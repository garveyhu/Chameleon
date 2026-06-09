"""agentkit 脱平台独立运行 —— 装上内部 SDK（workspace 可编辑装）即可在本机脱平台跑 @agent，
便于作者提交进站前的本地自测。

`StandaloneTransport` 是 `RuntimeTransport` 的「无平台」实现：模型走作者自带的 LangChain chat
model（自己的 key），记忆走本地 dict，知识库走传入的本地 Doc 列表，工具循环是真 ReAct，子
智能体走本地注册表。无需连 Chameleon 站点 / dev 服务——让作者在本机 30 行跑通、迭代，再原样
提交到平台（同一份 handle 代码，换 transport 即换运行环境）。

    from chameleon.agentkit import agent, AgentRun, ModelSlot
    from chameleon.agentkit.standalone import StandaloneTransport, run_standalone
    from langchain_openai import ChatOpenAI

    @agent(key="hello", name="hi", models=[ModelSlot("chat", "对话")])
    async def handle(ctx: AgentRun):
        async for d in ctx.stream(system="你是助手", user=ctx.query):
            yield d

    t = StandaloneTransport(model=ChatOpenAI(model="gpt-4o-mini"))
    print(await run_standalone(handle, "你好", transport=t))

平台专属能力（多模态生成）standalone 下显式报错而非静默——脱平台不可用是诚实边界。
公共面 `chameleon.agentkit.standalone` 与 `chameleon.agentkit` 一样属冻结契约（只增不改）。
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from typing import Any, Callable

from chameleon.agentkit._runtime import (
    AgentRun,
    RuntimeTransport,
    _degenerate_memory_search,
)
from chameleon.agentkit._spec import Doc, MediaResult, MemoryHit, ToolSpec

_MAX_A2A_DEPTH = 5


class _NullSpan:
    async def __aenter__(self) -> _NullSpan:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


def _content_text(resp: Any) -> str:
    content = getattr(resp, "content", resp)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b["text"] if isinstance(b, dict) and isinstance(b.get("text"), str)
            else (b if isinstance(b, str) else "")
            for b in content
        )
    return str(content) if content is not None else ""


class StandaloneTransport(RuntimeTransport):
    """脱平台 transport：模型=作者自带 LangChain model，记忆/kb/子agent 本地，工具循环真 ReAct。

    Args:
        model: 作者自带的 LangChain chat model（鸭子类型：ainvoke/astream/bind_tools/
            with_structured_output）。所有 slot/model 名都路由到它（standalone 单模型）。
        kb_docs: 本地知识库文档；ctx.kb.search 做朴素子串打分检索。
        memory: 初始记忆 dict（进程内，transport 存活期持久）。
        agents: 本地子智能体注册表 {key: handler}，支撑 ctx.call_agent/gather/route/handoff。
        on_event: 可选事件回调（ctx.emit 透传），默认丢弃。
    """

    def __init__(
        self,
        *,
        model: Any,
        kb_docs: list[Doc] | None = None,
        memory: dict[str, Any] | None = None,
        agents: dict[str, Any] | None = None,
        on_event: Callable[[Any], None] | None = None,
        _depth: int = 0,
    ) -> None:
        if not (hasattr(model, "ainvoke") and hasattr(model, "astream")):
            raise TypeError(
                "StandaloneTransport(model=) 需一个 LangChain chat model（实现 ainvoke/astream/"
                "bind_tools/with_structured_output），例如 langchain_openai.ChatOpenAI(...)；"
                f"收到的是 {type(model).__name__}。"
            )
        self._model = model
        self._kb = list(kb_docs or [])
        self._memory: dict[str, Any] = dict(memory or {})
        self._agents = dict(agents or {})
        self._on_event = on_event
        self._depth = _depth

    def chat_model(self, *, slot: str | None = None, model: str | None = None) -> Any:
        return self._model

    def structured_model(
        self, *, slot: str | None = None, model: str | None = None, schema: type
    ) -> Any:
        return self._model.with_structured_output(schema)

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
        # 朴素本地检索：按 query 词在 doc.text 的命中数打分（standalone 不接向量库）。
        # ⚠️ 召回质量远不及平台 hybrid+向量+rerank，仅供本地冒烟；勿据此调 RAG prompt。
        terms = [w for w in query.lower().split() if w]
        if len(terms) <= 1 and query.strip():
            # 无空格分词（中文等 CJK）→ 退化为字符 bigram，避免整串 count 必为 0 召回空
            q = "".join(query.lower().split())
            terms = [q[i : i + 2] for i in range(len(q) - 1)] or [q]
        scored: list[tuple[float, Doc]] = []
        for d in self._kb:
            text = (getattr(d, "text", "") or "").lower()
            hits = sum(text.count(t) for t in terms) if terms else (1 if text else 0)
            score = hits / (len(terms) or 1)
            if score >= min_score and hits > 0:
                scored.append((score, d))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = [Doc(text=d.text, score=s, source=d.source, metadata=d.metadata) for s, d in scored]
        return out[: top_k or 5]

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
        # 真 ReAct：bind 本地 @tool → 模型出 tool_calls → 本地执行 → 回填续跑。standalone 无
        # 平台工具（platform_keys 忽略，仅本地工具）。ToolMessage 惰性 import（作者既传 langchain
        # 模型必已装 langchain_core；agentkit 核心保持 langchain-free）。
        from langchain_core.messages import ToolMessage

        by_name = {s.name: s for s in local_tools}
        if not local_tools:
            async for chunk in self._model.astream(messages):
                text = _content_text(chunk)
                if text:
                    yield text
            return
        tool_param = [
            {"type": "function", "function": {
                "name": s.name, "description": s.description, "parameters": s.parameters_schema}}
            for s in local_tools
        ]
        bound = self._model.bind_tools(tool_param)
        convo = list(messages)
        for _step in range(max_steps):
            resp = await bound.ainvoke(convo)
            calls = getattr(resp, "tool_calls", None) or []
            if not calls:
                text = _content_text(resp)
                if text:
                    yield text
                return
            convo.append(resp)
            for c in calls:
                name = c.get("name") or ""
                args = c.get("args") or {}
                self._emit_tool_event("tool_call", c)  # 对齐 run_with_tools 契约（评审9 🟠）
                spec = by_name.get(name)
                if spec is not None:
                    try:
                        data = await spec.handler(**args)
                        result: dict[str, Any] = {"ok": True, "data": data}
                    except Exception as e:  # noqa: BLE001
                        result = {"ok": False, "error": str(e)[:300]}
                else:
                    result = {"ok": False, "error": f"未知工具 {name}"}
                self._emit_tool_event("tool_result", {"name": name, "result": result})
                import json
                convo.append(ToolMessage(
                    content=json.dumps(result, ensure_ascii=False, default=str),
                    tool_call_id=c.get("id") or name,
                ))
        # 达步数上限收口
        final = await self._model.ainvoke(convo)
        text = _content_text(final)
        if text:
            yield text

    async def memory_get(self, key: str, default: Any = None) -> Any:
        return self._memory.get(key, default)

    async def memory_set(self, key: str, value: Any) -> None:
        self._memory[key] = value

    async def memory_all(self) -> dict[str, Any]:
        return dict(self._memory)

    async def memory_search(
        self, query: str, *, top_k: int = 5, min_score: float = 0.0
    ) -> list[MemoryHit]:
        return _degenerate_memory_search(
            self._memory, query, top_k=top_k, min_score=min_score
        )

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
        raise NotImplementedError(
            "ctx.media 多模态生成是平台专属能力（需 ComfyUI/DashScope 路由 + 对象存储），"
            "standalone 脱平台运行不可用；部署到 Chameleon 平台后自动可用。"
        )

    async def call_agent(self, target: str, *, input: str) -> str:
        # 本地子智能体：从 agents 注册表取 handler，构造子 AgentRun（共享 model/agents、memory
        # 传父**快照**——__init__ 浅拷贝，子改不回写父，与平台 end_user 跨 agent 共享 kv 不同；
        # 深度 +1）跑其 handle 并收集答案。深度红线防无限递归。
        if target not in self._agents:
            raise RuntimeError(
                f"standalone 下子智能体 {target!r} 未在 StandaloneTransport(agents=...) 注册"
            )
        if self._depth >= _MAX_A2A_DEPTH:
            raise RuntimeError(f"A2A 嵌套深度超限（>{_MAX_A2A_DEPTH}）")
        child_t = StandaloneTransport(
            model=self._model, kb_docs=self._kb, memory=self._memory,
            agents=self._agents, on_event=self._on_event, _depth=self._depth + 1,
        )
        handler = self._agents[target]
        run = AgentRun(
            transport=child_t,
            agent_key=target,
            query=input,
            messages=[], history=[], session_id=None, config={},
        )
        result = handler().handle(run) if isinstance(handler, type) else handler(run)
        if inspect.isasyncgen(result):
            return "".join([c async for c in result])
        return (await result) or ""

    def span(self, name: str, *, type: str = "span") -> Any:
        return _NullSpan()

    def track_usage(self, usage: dict[str, int] | None) -> None:
        return

    def emit(self, event: Any) -> None:
        if self._on_event is not None:
            self._on_event(event)

    def _emit_tool_event(self, etype: str, data: dict[str, Any]) -> None:
        """ReAct 循环里发 tool_call/tool_result 事件（对齐 run_with_tools 契约，经 on_event 透出）。"""
        from chameleon.core.runtime_types import StreamEvent, StreamEventType

        try:
            self.emit(StreamEvent(type=StreamEventType(etype), data=data))
        except Exception:  # noqa: BLE001  事件透传不应影响主流程
            pass


async def run_standalone(
    target: Any,
    query: str,
    *,
    transport: StandaloneTransport,
    config: dict[str, Any] | None = None,
    history: list[Any] | None = None,
    session_id: str | None = None,
) -> str:
    """脱平台跑一个 @agent，返回完整答案文本（流式自动拼接）。"""
    run = AgentRun(
        transport=transport,
        agent_key=getattr(getattr(target, "__agent_manifest__", None), "key", "standalone"),
        query=query,
        messages=[], history=list(history or []),
        session_id=session_id, config=dict(config or {}),
    )
    result = target().handle(run) if isinstance(target, type) else target(run)
    if inspect.isasyncgen(result):
        return "".join([c async for c in result])
    return (await result) or ""
