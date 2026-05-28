"""运行时契约 —— AgentRun（作者面）与 RuntimeTransport（可插拔后端）。

Phase 0：仅定义公共签名 + 抽象，**不接实现**。
- `RuntimeTransport`：ctx 背后的资源解析 + 观测后端，两种实现（后续 phase）：
    · InProcessTransport：站内进程内，直连 routing / kb / observe
    · HttpDevTransport：本地自测，HTTP 回调 dev 服务 /v1/dev/{llm,kb,trace}
- `AgentRun`：注入给作者 `handle(ctx)` 的上下文；模型 / KB / trace 隐式从这里拿。

模型 / KB 解析全部落到平台「已配置资源池」，code/kb_key 校验，非任填。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Protocol

from chameleon.agentkit._spec import Doc

if TYPE_CHECKING:
    from chameleon.providers.base.types import Message, StreamEvent


class KbHandle(Protocol):
    """`ctx.kb` —— 知识库检索门面。"""

    async def search(
        self,
        query: str,
        *,
        kbs: list[str] | None = None,
        top_k: int | None = None,
        min_score: float = 0.0,
    ) -> list[Doc]:
        """kbs 给定=代码点名这些已配置 KB；否则用该 agent web 关联的 KB。"""
        ...


class RuntimeTransport(ABC):
    """ctx 背后的可插拔后端：解析已配置资源 + 观测。"""

    @abstractmethod
    def chat_model(self, *, slot: str | None = None, model: str | None = None) -> Any:
        """解析并返回配置好的 LangChain chat model。

        - slot：走该 agent 的绑定链（web 绑定 → 槽 default → 系统默认）。
        - model：直接点名某「已配置且启用」模型 code（= `llm_by_name`），校验非法即报错。
        - 两者互斥；都不给 = 系统默认（= `llm()`）。
        """
        ...

    @abstractmethod
    async def kb_search(
        self,
        query: str,
        *,
        kbs: list[str] | None = None,
        top_k: int | None = None,
        min_score: float = 0.0,
    ) -> list[Doc]:
        """检索；自动记 citation。kbs 校验须命中已配置 KB。"""
        ...

    @abstractmethod
    def span(self, name: str, *, type: str = "span") -> Any:
        """打开一个 observe span（async context manager）。"""
        ...

    @abstractmethod
    def emit(self, event: StreamEvent) -> None:
        """透传一个自定义 StreamEvent 到输出流。"""
        ...


class AgentRun:
    """注入给作者 `handle(ctx)` / `astream` 的运行时上下文。

    绑定「本 agent 的页面配置 + 本次请求」；模型 / KB / trace 都从这里隐式拿，
    作者不 import `llm()` / `search_kb()`、不传 agent_key、不手写 trace。
    """

    def __init__(
        self,
        *,
        transport: RuntimeTransport,
        agent_key: str,
        query: str,
        messages: list[Message],
        history: list[Message],
        session_id: str | None,
        config: dict[str, Any],
        attachments: list[dict[str, Any]] | None = None,
    ) -> None:
        self._t = transport
        self.agent_key = agent_key
        self.query = query
        self.messages = messages
        self.history = history
        self.session_id = session_id
        self.config = config
        #: 本次调用附带的附件原始 dict（{object_url, filename, mime, size}）。
        #: 图/音已由 service 翻进 messages 多模态 ContentBlock，作者主要拿这里
        #: 的元信息做条件分支；文档/数据类异步入临时 KB，通过 ctx.kb.search()
        #: 也能拿到检索结果。
        self.attachments: list[dict[str, Any]] = attachments or []

    # —— 模型（slot=走绑定链；model=点名已配置 code，二选一）——

    def llm(self, slot: str = "chat", *, model: str | None = None) -> Any:
        """低层：返回配置好的 LangChain chat model，可任意 LCEL 组合。"""
        return self._t.chat_model(slot=None if model else slot, model=model)

    async def complete(
        self,
        *,
        slot: str = "chat",
        model: str | None = None,
        system: str | None = None,
        user: str,
        context: Any = None,
        **kw: Any,
    ) -> str:
        """高层糖：一次性出文本，自动 generation span + usage。"""
        chat = self._t.chat_model(slot=None if model else slot, model=model)
        msgs = self._build_messages(system, user, context)
        async with self._t.span("llm.complete", type="span"):
            resp = await chat.ainvoke(msgs, **kw)
        return _content_to_text(resp)

    async def stream(
        self,
        *,
        slot: str = "chat",
        model: str | None = None,
        system: str | None = None,
        user: str,
        context: Any = None,
        **kw: Any,
    ) -> AsyncIterator[str]:
        """高层糖：流式出文本（逐增量 yield），自动 span + usage。"""
        chat = self._t.chat_model(slot=None if model else slot, model=model)
        msgs = self._build_messages(system, user, context)
        async with self._t.span("llm.stream", type="span"):
            async for chunk in chat.astream(msgs, **kw):
                text = _content_to_text(chunk)
                if text:
                    yield text

    def _build_messages(
        self, system: str | None, user: str, context: Any
    ) -> list[tuple[str, str]]:
        """组装 (role, content) 列表 —— system + history + 本轮 user（含可选 context）。

        不依赖 langchain：LangChain chat model 的 ainvoke/astream 接受 (role, content) 元组。
        """
        msgs: list[tuple[str, str]] = []
        if system:
            msgs.append(("system", system))
        for m in self.history:
            role = getattr(m, "role", "user")
            if role not in ("system", "user", "assistant"):
                continue
            msgs.append((role, m.text()))
        user_text = user
        if context:
            ctx_text = context if isinstance(context, str) else _docs_to_text(context)
            user_text = f"参考资料：\n{ctx_text}\n\n问题：{user}"
        msgs.append(("user", user_text))
        return msgs

    # —— 知识库 ——

    @property
    def kb(self) -> KbHandle:
        return _KbProxy(self._t)

    # —— 追踪（直接转发 transport，Phase 0 即可用其抽象契约）——

    def span(self, name: str, *, type: str = "span") -> Any:
        """打开一段 observe span（async context manager）。"""
        return self._t.span(name, type=type)

    def emit(self, event: StreamEvent) -> None:
        """透传一个自定义 StreamEvent。"""
        self._t.emit(event)


class _KbProxy:
    """`ctx.kb` 的实现：把 search 转发给 transport（结构上满足 KbHandle）。"""

    def __init__(self, transport: RuntimeTransport) -> None:
        self._t = transport

    async def search(
        self,
        query: str,
        *,
        kbs: list[str] | None = None,
        top_k: int | None = None,
        min_score: float = 0.0,
    ) -> list[Doc]:
        return await self._t.kb_search(
            query, kbs=kbs, top_k=top_k, min_score=min_score
        )


def _content_to_text(resp: Any) -> str:
    """从 LangChain message / chunk 取纯文本（content 可能是 str 或 block 列表）。"""
    content = getattr(resp, "content", resp)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for b in content:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict) and isinstance(b.get("text"), str):
                parts.append(b["text"])
        return "".join(parts)
    return str(content) if content is not None else ""


def _docs_to_text(docs: Any) -> str:
    """把 ctx.kb.search 的结果（list[Doc]）拼成参考资料文本。"""
    out: list[str] = []
    for d in docs or []:
        text = getattr(d, "text", None)
        out.append(text if isinstance(text, str) else str(d))
    return "\n---\n".join(out)
