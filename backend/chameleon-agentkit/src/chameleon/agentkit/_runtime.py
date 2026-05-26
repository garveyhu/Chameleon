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
    ) -> None:
        self._t = transport
        self.agent_key = agent_key
        self.query = query
        self.messages = messages
        self.history = history
        self.session_id = session_id
        self.config = config

    # —— 模型（slot=走绑定链；model=点名已配置 code，二选一）——

    def llm(self, slot: str = "chat", *, model: str | None = None) -> Any:
        """低层：返回配置好的 LangChain chat model，可任意 LCEL 组合。"""
        raise NotImplementedError("Phase 1")

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
        raise NotImplementedError("Phase 1")

    def stream(
        self,
        *,
        slot: str = "chat",
        model: str | None = None,
        system: str | None = None,
        user: str,
        context: Any = None,
        **kw: Any,
    ) -> AsyncIterator[str]:
        """高层糖：流式出文本，自动 span + usage。"""
        raise NotImplementedError("Phase 1")

    # —— 知识库 ——

    @property
    def kb(self) -> KbHandle:
        raise NotImplementedError("Phase 2")

    # —— 追踪（直接转发 transport，Phase 0 即可用其抽象契约）——

    def span(self, name: str, *, type: str = "span") -> Any:
        """打开一段 observe span（async context manager）。"""
        return self._t.span(name, type=type)

    def emit(self, event: StreamEvent) -> None:
        """透传一个自定义 StreamEvent。"""
        self._t.emit(event)
