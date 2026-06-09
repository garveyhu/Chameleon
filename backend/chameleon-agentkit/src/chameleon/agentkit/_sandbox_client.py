"""沙箱子进程内的 ctx transport —— 每个资源调用经 stdio JSON-RPC 回主进程 broker。

子进程跑作者 handle(ctx)，ctx 的模型/工具/KB 等调用不在子进程本地解析（子进程无凭据），
而是发 rpc 帧到主进程 broker、阻塞读 rpc_result。复用 AgentRun.complete/stream 不变：
chat_model() 返回的假模型 ainvoke 即做一次 rpc 往返。

协议见 docs/plans/2026-06-08-sandbox-phase2-design.md §2。本模块在 agentkit，子进程只需
agentkit + 作者包，无需 integrations/providers（轻量 + 凭据隔离）。

Slice 1：支持 chat（complete 底层）+ emit；其余 ctx 能力后续分片接入。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from chameleon.agentkit._runtime import RuntimeTransport


def to_wire_messages(messages: Any) -> list[dict[str, Any]]:
    """把 (role, content) 元组 / langchain message / dict 归一成 OpenAI 风格 dict（过线）。"""
    out: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, dict):
            out.append(m)
        elif isinstance(m, tuple) and len(m) == 2:
            out.append({"role": m[0], "content": m[1]})
        else:
            role = getattr(m, "type", "user")
            role = {"human": "user", "ai": "assistant"}.get(role, role)
            out.append({"role": role, "content": getattr(m, "content", str(m))})
    return out


class _Msg:
    def __init__(self, content: str) -> None:
        self.content = content
        self.tool_calls: list[Any] = []


class _SandboxChatModel:
    def __init__(self, transport: SandboxClientTransport, slot: str | None, model: str | None) -> None:
        self._t = transport
        self._slot = slot
        self._model = model

    async def ainvoke(self, messages: Any, **_kw: Any) -> _Msg:
        data = await self._t._rpc(
            "chat",
            {"messages": to_wire_messages(messages), "slot": self._slot, "model": self._model},
        )
        return _Msg(data if isinstance(data, str) else (data or {}).get("content", ""))

    async def astream(self, messages: Any, **_kw: Any) -> AsyncIterator[_Msg]:
        async for chunk in self._t._rpc_stream(
            "chat_stream",
            {"messages": to_wire_messages(messages), "slot": self._slot, "model": self._model},
        ):
            yield _Msg(chunk if isinstance(chunk, str) else "")


class _NullSpan:
    async def __aenter__(self) -> _NullSpan:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


#: 帧 IO 注入：send_fn 写一帧到 stdout；recv_fn 读下一帧（dict）。便于单测换内存假实现。
SendFn = Callable[[dict[str, Any]], None]
RecvFn = Callable[[], Awaitable[dict[str, Any]]]


_STREAM_DONE = object()  # _rpc_stream 队列的结束哨兵（区别于 None chunk）


class SandboxClientTransport(RuntimeTransport):
    """子进程内 ctx transport：资源调用 → stdio JSON-RPC 往返；emit → event 帧。

    send_fn/recv_fn：底层帧 IO（child 注入真实 stdout 写 + stdin 读）。非流式 rpc 发一帧读
    一帧 rpc_result；流式（chat_stream）发一帧读多帧 stream_chunk 直到 rpc_result。
    """

    def __init__(
        self, *, send_fn: SendFn, recv_fn: RecvFn, emit_fn: Callable[[dict[str, Any]], None]
    ) -> None:
        self._send = send_fn
        self._recv = recv_fn
        self._emit_fn = emit_fn
        self._rpc_id = 0
        # 单读帧泵多路复用：泵独占 recv_fn、按 id 把帧 demux 到 per-rid 等待者。这样并发 ctx
        # 调用（作者 asyncio.gather）不偷帧（评审7 🟠），且**不持锁跨 yield**——流式期间嵌套
        # rpc（async for ctx.stream(): await ctx.kb.search()）不会重入死锁（评审8 🔴）。
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._streams: dict[int, asyncio.Queue[Any]] = {}
        self._pump_task: asyncio.Task[None] | None = None

    def _next_id(self) -> int:
        self._rpc_id += 1
        return self._rpc_id

    def _ensure_pump(self) -> None:
        if self._pump_task is None:
            self._pump_task = asyncio.ensure_future(self._pump())

    async def _pump(self) -> None:
        """读帧泵：独占 recv，按 frame.id 派发到对应 Future（rpc）/ Queue（stream）。"""
        try:
            while True:
                frame = await self._recv()
                if frame is None:
                    raise RuntimeError("sandbox 通道关闭")
                fid = frame.get("id")
                ft = frame.get("t")
                if ft == "stream_chunk":
                    q = self._streams.get(fid)
                    if q is not None:
                        q.put_nowait(frame.get("chunk"))
                elif ft == "rpc_result":
                    ok, err, data = frame.get("ok"), frame.get("error"), frame.get("data")
                    fut = self._pending.pop(fid, None)
                    if fut is not None and not fut.done():
                        if ok:
                            fut.set_result(data)
                        else:
                            fut.set_exception(RuntimeError(err or "sandbox rpc 失败"))
                    else:
                        q = self._streams.get(fid)
                        if q is not None:
                            q.put_nowait(
                                _STREAM_DONE if ok else RuntimeError(err or "sandbox rpc 失败")
                            )
        except Exception as e:  # noqa: BLE001  recv EOF/失败：让所有等待者失败，别永久挂
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(e)
            for q in self._streams.values():
                q.put_nowait(e)

    async def _rpc(self, method: str, args: dict[str, Any]) -> Any:
        self._ensure_pump()
        rid = self._next_id()
        fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        self._send({"t": "rpc", "id": rid, "method": method, "args": args})
        return await fut

    async def _rpc_stream(self, method: str, args: dict[str, Any]) -> AsyncIterator[Any]:
        self._ensure_pump()
        rid = self._next_id()
        q: asyncio.Queue[Any] = asyncio.Queue()
        self._streams[rid] = q
        self._send({"t": "rpc", "id": rid, "method": method, "args": args})
        try:
            while True:
                item = await q.get()
                if item is _STREAM_DONE:
                    return
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            self._streams.pop(rid, None)  # 消费者提前 break 也清理，不泄漏

    def chat_model(self, *, slot: str | None = None, model: str | None = None) -> Any:
        return _SandboxChatModel(self, slot, model)

    def emit(self, event: Any) -> None:
        etype = getattr(event, "type", None)
        etype = getattr(etype, "value", etype)
        data = getattr(event, "data", None)
        self._emit_fn({"t": "event", "event": {"type": str(etype), "data": data}})

    def span(self, name: str, *, type: str = "span") -> Any:
        return _NullSpan()

    def track_usage(self, usage: dict[str, int] | None) -> None:
        return  # Slice 3：经 rpc 上报计入预算闸

    async def kb_search(
        self, query, *, kbs=None, top_k=None, min_score=0.0, mode=None, rerank=None, expand=0, hyde=False,
    ):  # noqa: ANN001, ANN201
        from chameleon.agentkit._spec import Doc

        rows = await self._rpc(
            "kb_search",
            {"query": query, "kbs": kbs, "top_k": top_k, "min_score": min_score,
             "mode": mode, "rerank": rerank, "expand": expand, "hyde": hyde},
        )
        return [
            Doc(
                text=d.get("text", ""), score=d.get("score", 0.0),
                source=d.get("source"), metadata=d.get("metadata") or {},
            )
            for d in (rows or [])
        ]

    # —— 后续分片经 rpc 接入 ——

    def structured_model(self, *, slot=None, model=None, schema):  # noqa: ANN001, ANN201
        raise NotImplementedError("sandbox Slice 2+：structured 经 rpc")

    async def run_tool_loop(  # noqa: ANN201
        self, *, messages, slot, model, platform_keys, local_tools, max_steps, max_tokens=None,
    ):  # noqa: ANN001
        """ReAct 循环跑在子进程：每轮 chat_tools rpc（模型带工具）→ 本地 @tool 子进程执行 /
        平台工具经 run_tool rpc → 回填续跑。模型/平台工具凭据仍只在主进程 broker。"""
        local_by_name = {s.name: s for s in local_tools}
        local_schemas = [
            {"type": "function", "function": {
                "name": s.name, "description": s.description, "parameters": s.parameters_schema}}
            for s in local_tools
        ]
        convo = to_wire_messages(messages)
        for _step in range(max_steps):
            out = await self._rpc(
                "chat_tools",
                {"messages": convo, "slot": slot, "model": model,
                 "platform_tool_keys": list(platform_keys or []), "local_tool_schemas": local_schemas},
            ) or {}
            calls = out.get("tool_calls") or []
            if not calls:
                text = out.get("content") or ""
                if text:
                    yield text
                return
            convo.append({"role": "assistant", "content": out.get("content") or "", "tool_calls": calls})
            for c in calls:
                self._emit_fn({"t": "event", "event": {"type": "tool_call", "data": c}})
                name = c.get("name") or ""
                args = c.get("args") or {}
                if name in local_by_name:
                    try:
                        data = await local_by_name[name].handler(**args)
                        result = {"tool_key": name, "ok": True, "data": data, "error": None}
                    except Exception as e:  # noqa: BLE001
                        result = {"tool_key": name, "ok": False, "data": None, "error": str(e)}
                else:
                    result = await self._rpc("run_tool", {"name": name, "args": args})
                self._emit_fn({"t": "event", "event": {"type": "tool_result",
                                                       "data": {"name": name, "result": result}}})
                convo.append({"role": "tool", "tool_call_id": c.get("id") or name,
                              "content": json.dumps(result, ensure_ascii=False, default=str)})
        # 达上限收口（无强制工具）
        final = await self._rpc("chat", {"messages": convo, "slot": slot, "model": model})
        text = final if isinstance(final, str) else (final or {}).get("content", "")
        if text:
            yield text

    async def memory_get(self, key, default=None):  # noqa: ANN001, ANN201
        val = await self._rpc("memory_get", {"key": key})
        return val if val is not None else default

    async def memory_set(self, key, value):  # noqa: ANN001, ANN201
        await self._rpc("memory_set", {"key": key, "value": value})

    async def memory_all(self):  # noqa: ANN201
        return await self._rpc("memory_all", {}) or {}

    async def memory_search(self, query, *, top_k=5, min_score=0.0):  # noqa: ANN001, ANN201
        from chameleon.agentkit._spec import MemoryHit

        rows = await self._rpc(
            "memory_search", {"query": query, "top_k": top_k, "min_score": min_score}
        )
        return [
            MemoryHit(
                key=r.get("key", ""),
                value=r.get("value"),
                text=r.get("text", ""),
                score=float(r.get("score", 0.0)),
            )
            for r in (rows or [])
            if r.get("key")
        ]

    async def media_generate(self, *, kind, prompt, slot=None, model=None, params=None, input_images=None):  # noqa: ANN001, ANN201
        from chameleon.agentkit._spec import MediaResult

        d = await self._rpc(
            "media_generate",
            {"kind": kind, "prompt": prompt, "slot": slot, "model": model,
             "params": params, "input_images": input_images},
        ) or {}
        return MediaResult(
            url=d.get("url", ""), object_key=d.get("object_key", ""),
            media_kind=d.get("media_kind", kind), mime_type=d.get("mime_type"),
            filename=d.get("filename"),
        )

    async def call_agent(self, target, *, input):  # noqa: ANN001, ANN201
        return await self._rpc("call_agent", {"target": target, "input": input}) or ""

    async def gather(self, calls):  # noqa: ANN001, ANN201
        # 沙箱单 stdio 通道无多路复用：并发 _rpc 会乱序吞帧（评审7 🟠）+ 预算无均分会超支。
        # 故沙箱档**串行**委托 call_agent（正确性优先；真并行待 per-rid Future 读帧泵落地）。
        return [await self.call_agent(t, input=i) for t, i in calls]


def encode_frame(obj: dict[str, Any]) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, default=str) + "\n").encode("utf-8")


def decode_frame(line: bytes | str) -> dict[str, Any]:
    s = line.decode("utf-8") if isinstance(line, bytes) else line
    return json.loads(s)
