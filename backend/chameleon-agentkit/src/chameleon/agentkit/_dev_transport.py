"""HttpDevTransport —— 本地自测 transport（连 dev 服务 /v1/dev/*）。

作者本地用 `agentkit chat` 跑自己的 @agent 代码：代码不变，ctx 的模型 / KB / 工具
调用经本 transport HTTP 回调到站内 dev 端点，用平台已配置资源跑，无需本地凭据。

与 InProcessTransport（站内进程内）是「同一份作者代码两种跑法」的两端。工具循环
跑在这里（客户端），每轮的「绑工具 + 调一次模型」委托 dev 服务 /v1/dev/llm。

依赖 httpx（在 `chameleon-agentkit[dev]` extra 里）；仅 CLI / 本地自测时 import。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from chameleon.agentkit._runtime import RuntimeTransport
from chameleon.agentkit._spec import Doc, ToolSpec


class _NullSpan:
    async def __aenter__(self) -> _NullSpan:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _RemoteChatModel:
    """ctx.llm() 的 dev 实现：ainvoke/astream 经 /v1/dev/llm 调站内模型。"""

    def __init__(self, transport: HttpDevTransport, model: str | None) -> None:
        self._t = transport
        self._model = model

    async def ainvoke(self, messages: Any, **_kw: Any) -> Any:
        out = await self._t._post(
            "/v1/dev/llm",
            {"messages": _to_openai(messages), "model": self._model},
        )
        return _RemoteMsg(out.get("content") or "", out.get("tool_calls") or [])

    async def astream(self, messages: Any, **kw: Any) -> AsyncIterator[Any]:
        # dev 简化：一次出全文（本地自测够用；站内 InProcess 走真流式）
        resp = await self.ainvoke(messages, **kw)
        yield resp


class _RemoteMsg:
    def __init__(self, content: str, tool_calls: list[dict[str, Any]]) -> None:
        self.content = content
        self.tool_calls = tool_calls


def _to_openai(messages: Any) -> list[dict[str, Any]]:
    """把 (role, content) 元组列表 / 已是 dict 的列表归一成 OpenAI 风格 dict。"""
    out: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, dict):
            out.append(m)
        elif isinstance(m, tuple) and len(m) == 2:
            out.append({"role": m[0], "content": m[1]})
        else:  # langchain message-ish
            role = getattr(m, "type", "user")
            role = {"human": "user", "ai": "assistant"}.get(role, role)
            out.append({"role": role, "content": getattr(m, "content", str(m))})
    return out


class HttpDevTransport(RuntimeTransport):
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        agent_key: str = "dev",
        platform_tool_keys: list[str] | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._token = token
        self._agent_key = agent_key
        self._tool_keys = list(platform_tool_keys or [])
        self._pending: list[Any] = []

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(
                f"{self._base}{path}",
                json=body,
                headers={"X-Dev-Token": self._token},
            )
            r.raise_for_status()
            payload = r.json()
        # 站内统一响应包装：脱外层取 data
        return payload.get("data", payload) if isinstance(payload, dict) else payload

    def chat_model(self, *, slot: str | None = None, model: str | None = None) -> Any:
        # dev 不解析 slot 绑定链（无 DB 上下文）：slot 走系统默认，model 点名透传
        return _RemoteChatModel(self, model)

    def structured_model(
        self, *, slot: str | None = None, model: str | None = None, schema: type
    ) -> Any:
        raise NotImplementedError(
            "dev 模式暂不支持 ctx.complete(schema=...) 结构化输出；"
            "请在站内（提交后 InProcessTransport）验证该路径。"
        )

    async def kb_search(
        self,
        query: str,
        *,
        kbs: list[str] | None = None,
        top_k: int | None = None,
        min_score: float = 0.0,
        mode: str | None = None,
        rerank: bool | None = None,
        expand: int = 0,
        hyde: bool = False,
    ) -> list[Doc]:
        if not kbs:
            return []  # dev 无 agent 关联上下文，需显式 kbs
        out = await self._post(
            "/v1/dev/kb/search",
            {
                "query": query, "kbs": list(kbs), "top_k": top_k,
                "min_score": min_score, "mode": mode, "rerank": rerank,
                "expand": expand, "hyde": hyde,
            },
        )
        rows = out if isinstance(out, list) else out.get("data", [])
        return [
            Doc(
                text=d.get("text", ""),
                score=d.get("score", 0.0),
                source=d.get("source"),
                metadata=d.get("metadata") or {},
            )
            for d in rows
        ]

    async def run_tool_loop(
        self,
        *,
        messages: list[Any],
        slot: str | None,
        model: str | None,
        platform_keys: list[str],
        local_tools: list[ToolSpec],
        max_steps: int,
        max_tokens: int | None = None,  # dev 不强制预算，仅签名一致
    ) -> AsyncIterator[str]:
        plat = list(dict.fromkeys([*self._tool_keys, *(platform_keys or [])]))
        local_by_name = {s.name: s for s in local_tools}
        local_schemas = [
            {
                "type": "function",
                "function": {
                    "name": s.name,
                    "description": s.description,
                    "parameters": s.parameters_schema,
                },
            }
            for s in local_tools
        ]
        convo = _to_openai(messages)

        for _step in range(max_steps):
            out = await self._post(
                "/v1/dev/llm",
                {
                    "messages": convo,
                    "model": model,
                    "platform_tool_keys": plat,
                    "local_tool_schemas": local_schemas,
                },
            )
            calls = out.get("tool_calls") or []
            if not calls:
                text = out.get("content") or ""
                if text:
                    yield text
                return

            convo.append(
                {"role": "assistant", "content": out.get("content") or "", "tool_calls": calls}
            )
            for c in calls:
                self.emit({"type": "tool_call", "data": c})
                name = c.get("name") or ""
                args = c.get("args") or {}
                if name in local_by_name:
                    try:
                        data = await local_by_name[name].handler(**args)
                        result = {"tool_key": name, "ok": True, "data": data, "error": None}
                    except Exception as e:  # noqa: BLE001
                        result = {"tool_key": name, "ok": False, "data": None, "error": str(e)}
                else:
                    result = await self._post(
                        "/v1/dev/tools/exec", {"name": name, "args": args}
                    )
                self.emit({"type": "tool_result", "data": {"name": name, "result": result}})
                convo.append(
                    {
                        "role": "tool",
                        "tool_call_id": c.get("id") or name,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

        # 达上限：最后收口一次
        out = await self._post("/v1/dev/llm", {"messages": convo, "model": model})
        text = out.get("content") or ""
        if text:
            yield text

    async def memory_get(self, key: str, default: Any = None) -> Any:
        raise NotImplementedError("dev 模式暂不支持 ctx.memory；请在站内验证该路径。")

    async def memory_set(self, key: str, value: Any) -> None:
        raise NotImplementedError("dev 模式暂不支持 ctx.memory；请在站内验证该路径。")

    async def memory_all(self) -> dict[str, Any]:
        raise NotImplementedError("dev 模式暂不支持 ctx.memory；请在站内验证该路径。")

    async def media_generate(self, *, kind, prompt, slot=None, model=None, params=None, input_images=None):  # noqa: ANN001, ANN201
        raise NotImplementedError("dev 模式暂不支持 ctx.media；请在站内验证该路径。")

    async def call_agent(self, target: str, *, input: str) -> str:
        raise NotImplementedError(
            "dev 模式暂不支持 ctx.call_agent 子智能体调用；请在站内验证该路径。"
        )

    def span(self, name: str, *, type: str = "span") -> Any:
        return _NullSpan()

    def track_usage(self, usage: dict[str, int] | None) -> None:
        return  # dev 不上报 usage（本地自测无计费/预算语义）

    def emit(self, event: Any) -> None:
        self._pending.append(event)

    def drain(self) -> list[Any]:
        out, self._pending = self._pending, []
        return out
