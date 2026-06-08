"""沙箱子进程内的 ctx transport —— 每个资源调用经 stdio JSON-RPC 回主进程 broker。

子进程跑作者 handle(ctx)，ctx 的模型/工具/KB 等调用不在子进程本地解析（子进程无凭据），
而是发 rpc 帧到主进程 broker、阻塞读 rpc_result。复用 AgentRun.complete/stream 不变：
chat_model() 返回的假模型 ainvoke 即做一次 rpc 往返。

协议见 docs/plans/2026-06-08-sandbox-phase2-design.md §2。本模块在 agentkit，子进程只需
agentkit + 作者包，无需 integrations/providers（轻量 + 凭据隔离）。

Slice 1：支持 chat（complete 底层）+ emit；其余 ctx 能力后续分片接入。
"""

from __future__ import annotations

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

    def _next_id(self) -> int:
        self._rpc_id += 1
        return self._rpc_id

    async def _rpc(self, method: str, args: dict[str, Any]) -> Any:
        rid = self._next_id()
        self._send({"t": "rpc", "id": rid, "method": method, "args": args})
        while True:
            frame = await self._recv()
            if frame.get("t") == "rpc_result" and frame.get("id") == rid:
                if not frame.get("ok"):
                    raise RuntimeError(frame.get("error") or f"sandbox rpc 失败: {method}")
                return frame.get("data")

    async def _rpc_stream(self, method: str, args: dict[str, Any]) -> AsyncIterator[Any]:
        rid = self._next_id()
        self._send({"t": "rpc", "id": rid, "method": method, "args": args})
        while True:
            frame = await self._recv()
            if frame.get("id") != rid:
                continue
            if frame.get("t") == "stream_chunk":
                yield frame.get("chunk")
            elif frame.get("t") == "rpc_result":
                if not frame.get("ok"):
                    raise RuntimeError(frame.get("error") or f"sandbox rpc 失败: {method}")
                return

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

    def run_tool_loop(self, *, messages, slot, model, platform_keys, local_tools, max_steps, max_tokens=None):  # noqa: ANN001, ANN201
        raise NotImplementedError("sandbox Slice 2：工具循环（在子进程跑，模型/平台工具经 rpc）")

    async def memory_get(self, key, default=None):  # noqa: ANN001, ANN201
        raise NotImplementedError("sandbox Slice 3：memory")

    async def memory_set(self, key, value):  # noqa: ANN001, ANN201
        raise NotImplementedError("sandbox Slice 3：memory")

    async def memory_all(self):  # noqa: ANN201
        raise NotImplementedError("sandbox Slice 3：memory")

    async def media_generate(self, *, kind, prompt, slot=None, model=None, params=None, input_images=None):  # noqa: ANN001, ANN201
        raise NotImplementedError("sandbox Slice 3：media")

    async def call_agent(self, target, *, input):  # noqa: ANN001, ANN201
        raise NotImplementedError("sandbox Slice 3：call_agent")


def encode_frame(obj: dict[str, Any]) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, default=str) + "\n").encode("utf-8")


def decode_frame(line: bytes | str) -> dict[str, Any]:
    s = line.decode("utf-8") if isinstance(line, bytes) else line
    return json.loads(s)
