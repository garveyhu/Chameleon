"""agentkit 作者测试套件 —— 离线、确定性地为自己的 @agent 写单测。

无需连 dev 服务 / 站内：`FakeTransport` 是 `RuntimeTransport` 的第三种实现（继
InProcess / HttpDev），可编程模型回复 / KB 命中 / 工具结果 / 记忆，并记录所有调用。
对标 Pydantic AI 的 TestModel。

    from chameleon.agentkit.testing import make_run, FakeTransport, collect
    from my_pkg.agent import handle

    async def test_answers():
        t = FakeTransport(replies=["北京晴"])
        run = make_run(handle, query="北京天气", transport=t)
        out = await collect(handle(run))
        assert "晴" in out

公共面：`chameleon.agentkit.testing` 与 `chameleon.agentkit` 一样属冻结契约（只增不改）。
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from typing import Any

from chameleon.agentkit._runtime import AgentRun, RuntimeTransport
from chameleon.agentkit._spec import Doc, MediaResult, ToolSpec


class _FakeMsg:
    def __init__(self, content: str) -> None:
        self.content = content
        self.tool_calls: list[Any] = []


class _FakeChat:
    """ctx.llm() 的假实现：ainvoke/astream 顺序吐编程好的 replies。"""

    def __init__(self, transport: FakeTransport) -> None:
        self._t = transport

    async def ainvoke(self, messages: Any, **_kw: Any) -> _FakeMsg:
        self._t.invocations.append(("ainvoke", messages))
        return _FakeMsg(self._t._next_reply())

    async def astream(self, messages: Any, **_kw: Any) -> AsyncIterator[_FakeMsg]:
        self._t.invocations.append(("astream", messages))
        yield _FakeMsg(self._t._next_reply())


class _FakeStructured:
    def __init__(self, value: Any) -> None:
        self._value = value

    async def ainvoke(self, messages: Any, **_kw: Any) -> Any:
        return self._value


class _NullSpan:
    async def __aenter__(self) -> _NullSpan:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class FakeTransport(RuntimeTransport):
    """离线测试 transport：可编程回复 / KB / 工具 / 记忆 / 媒体 / 子 agent，记录调用。

    Attributes:
        invocations: 模型调用记录 [(kind, messages), ...]
        tool_invocations: 本地工具调用记录 [(name, args, result), ...]
        emitted: 透传的事件 / citation 列表
    """

    def __init__(
        self,
        *,
        replies: list[str] | None = None,
        kb: list[Doc] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        structured: Any = None,
        memory: dict[str, Any] | None = None,
        call_agent_reply: str = "",
    ) -> None:
        self._replies = list(replies or [])
        self._reply_i = 0
        self._kb = list(kb or [])
        self._tool_calls = list(tool_calls or [])  # [{name, args}] 编程的工具调用
        self._structured = structured
        self._memory: dict[str, Any] = dict(memory or {})
        self._call_agent_reply = call_agent_reply
        self.invocations: list[tuple[str, Any]] = []
        self.tool_invocations: list[tuple[str, dict, Any]] = []
        self.emitted: list[Any] = []
        self.usage_tracked: list[dict] = []

    def _next_reply(self) -> str:
        if not self._replies:
            return ""
        r = self._replies[min(self._reply_i, len(self._replies) - 1)]
        self._reply_i += 1
        return r

    def chat_model(self, *, slot: str | None = None, model: str | None = None) -> Any:
        return _FakeChat(self)

    def structured_model(
        self, *, slot: str | None = None, model: str | None = None, schema: type
    ) -> Any:
        return _FakeStructured(self._structured)

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
        return list(self._kb)

    async def run_tool_loop(
        self,
        *,
        messages: list[Any],
        slot: str | None,
        model: str | None,
        platform_keys: list[str],
        local_tools: list[ToolSpec],
        max_steps: int,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        # 简化但确定：依次执行编程好的 tool_calls（命中本地工具），最后 yield reply。
        # 注意：与站内 InProcess 不同，这里**不 emit** tool_call/tool_result/step 事件——
        # 断言工具调用请用 self.tool_invocations，勿用 self.emitted（后者会是空，假阴性）。
        by_name = {s.name: s for s in local_tools}
        for tc in self._tool_calls:
            spec = by_name.get(tc.get("name"))
            if spec is None:
                continue
            args = tc.get("args") or {}
            result = await spec.handler(**args)
            self.tool_invocations.append((tc["name"], args, result))
        reply = self._next_reply()
        if reply:
            yield reply

    async def memory_get(self, key: str, default: Any = None) -> Any:
        return self._memory.get(key, default)

    async def memory_set(self, key: str, value: Any) -> None:
        self._memory[key] = value

    async def memory_all(self) -> dict[str, Any]:
        return dict(self._memory)

    async def media_generate(
        self,
        *,
        kind: str,
        prompt: str,
        slot: str | None = None,
        model: str | None = None,
        params: dict[str, Any] | None = None,
        input_images: list[str] | None = None,
    ) -> MediaResult:
        return MediaResult(
            url=f"fake://{kind}/{prompt[:16]}",
            object_key=f"fake/{kind}",
            media_kind=kind,
        )

    async def call_agent(self, target: str, *, input: str) -> str:
        self.invocations.append(("call_agent", (target, input)))
        return self._call_agent_reply

    def span(self, name: str, *, type: str = "span") -> Any:
        return _NullSpan()

    def track_usage(self, usage: dict[str, int] | None) -> None:
        if usage:
            self.usage_tracked.append(usage)

    def emit(self, event: Any) -> None:
        self.emitted.append(event)


def make_run(
    target: Any,
    *,
    query: str,
    transport: RuntimeTransport | None = None,
    config: dict[str, Any] | None = None,
    history: list[Any] | None = None,
    session_id: str | None = None,
) -> AgentRun:
    """从 @agent 目标 / 任意输入构造一个可直接 await 的 AgentRun（默认 FakeTransport）。"""
    t = transport or FakeTransport()
    return AgentRun(
        transport=t,
        agent_key=getattr(getattr(target, "__agent_manifest__", None), "key", "test"),
        query=query,
        messages=[],
        history=list(history or []),
        session_id=session_id,
        config=dict(config or {}),
    )


async def collect(result: Any) -> str:
    """把作者 handler 返回（async generator / coroutine）收成完整文本，供断言。"""
    if inspect.isasyncgen(result):
        parts: list[str] = []
        async for chunk in result:
            parts.append(chunk if isinstance(chunk, str) else str(chunk))
        return "".join(parts)
    text = await result
    return text or ""
