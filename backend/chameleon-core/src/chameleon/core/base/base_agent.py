"""BaseAgent —— Chameleon 本地 agent 抽象基类

★ 关键设计：**框架不锁死 LangGraph**

本地 agent 的契约就是一个 async generator：

    async def astream(ctx) -> AsyncIterator[StreamEvent]:
        yield ...

具体怎么产生 StreamEvent，**agent 自由选择**：
- **范式 A**（最灵活）：直接 yield —— 纯 Python 异步循环
- **范式 B**（适合复杂流程）：用 LangGraph CompiledGraph，配合 bridges 工具
- **范式 C**（适合 LCEL 链式）：用 LangChain Runnable，配合 bridges 工具
- **混合**：astream 内自由组合，比如先 LangGraph 跑前置节点，再纯 Python yield 收尾

BaseAgent 提供：
1. 抽象 `astream(cls, ctx)` —— 必须实现
2. `get_metadata()` —— 元数据
3. `from_langgraph_graph(ctx, graph)` —— LangGraph 桥的 classmethod 包装
4. `from_runnable(ctx, runnable, ...)` —— LangChain Runnable 桥的 classmethod 包装
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chameleon.providers.base.types import InvokeContext, StreamEvent


@dataclass
class AgentConfigOption:
    """agent 配置选项（前端可渲染配置面板）"""

    id: str
    type: str  # toggle / select / button / datasource / number / text
    label: str
    description: str | None = None
    required: bool = False
    default: Any = None
    depends_on: str | None = None
    icon: str | None = None
    icon_only: bool = False
    hide_tooltip: bool = False
    options: list[dict[str, str]] | None = None


@dataclass
class AgentMetadata:
    """agent 元数据"""

    id: str
    name: str
    description: str
    icon: str | None = None
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    config_options: list[AgentConfigOption] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "version": self.version,
            "tags": list(self.tags),
            "config_options": [
                {
                    "id": o.id,
                    "type": o.type,
                    "label": o.label,
                    "description": o.description,
                    "required": o.required,
                    "default": o.default,
                    "depends_on": o.depends_on,
                    "icon": o.icon,
                    "icon_only": o.icon_only,
                    "options": o.options,
                }
                for o in self.config_options
            ],
        }


class BaseAgent(ABC):
    """Chameleon 本地 agent 基类

    必须实现：
    - get_metadata() classmethod
    - astream(ctx) classmethod —— async generator 产 StreamEvent

    可选实现（用于自动 fallback）：
    - build_graph() classmethod —— LangGraph CompiledGraph（默认 astream 用它）
    - build_runnable() classmethod —— LangChain Runnable（默认 astream 用它）

    如果只实现 build_graph 或 build_runnable 之一，BaseAgent 默认的 astream
    会自动调用对应的桥工具——你完全不写 astream 代码也能跑。
    """

    @classmethod
    @abstractmethod
    def get_metadata(cls) -> AgentMetadata:
        """返 AgentMetadata；id 即 agent_key"""

    @classmethod
    async def astream(cls, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        """产生 StreamEvent 流。

        默认实现：
        - 如果子类有 build_graph() → 调 LangGraph 桥
        - 如果子类有 build_runnable() → 调 LangChain Runnable 桥
        - 否则 NotImplementedError

        子类可自由 override 此方法做完全自定义流式输出。
        """
        if hasattr(cls, "build_graph") and callable(cls.build_graph):
            async for ev in cls.from_langgraph_graph(ctx, cls.build_graph()):
                yield ev
            return

        if hasattr(cls, "build_runnable") and callable(cls.build_runnable):
            async for ev in cls.from_runnable(ctx, cls.build_runnable()):
                yield ev
            return

        raise NotImplementedError(
            f"{cls.__name__} must implement astream() OR build_graph() OR build_runnable()"
        )

    # ── KB 检索（关联 KB → 跨 KB merge top_k） ────────────────

    @classmethod
    async def retrieve(
        cls,
        ctx: "InvokeContext",
        query: str,
        *,
        top_k: int | None = None,
        min_score: float = 0.0,
    ) -> list[Any]:
        """跨 ctx.agent_def 所有挂载 KB 的向量检索；按 score 合并 top_k。

        没挂 KB → 返空 list。
        """
        from chameleon.integrations.knowledge import (
            list_linked_kb_metas,
            search_kb,
        )

        agent_key = ctx.agent_def.key
        metas = await list_linked_kb_metas(agent_key)
        if not metas:
            return []
        merged: list[Any] = []
        for meta in metas:
            k = top_k or meta.chunk_size and 5  # 默认 5
            hits = await search_kb(
                meta.kb_key, query, top_k=k, min_score=min_score
            )
            merged.extend(hits)
        merged.sort(key=lambda h: getattr(h, "score", 0.0), reverse=True)
        return merged[: (top_k or 5)]

    # ── 内置范式桥（classmethod 形式，方便子类直接 yield from） ─

    @classmethod
    async def from_langgraph_graph(
        cls, ctx: InvokeContext, graph: Any, **kwargs: Any
    ) -> AsyncIterator[StreamEvent]:
        """LangGraph 桥（agent 直接用）

        用法：
            async def astream(cls, ctx):
                graph = cls._build()
                async for ev in cls.from_langgraph_graph(ctx, graph):
                    yield ev
        """
        from chameleon.integrations.bridges import astream_from_langgraph_graph

        async for ev in astream_from_langgraph_graph(ctx, graph, **kwargs):
            yield ev

    @classmethod
    async def from_runnable(
        cls,
        ctx: InvokeContext,
        runnable: Any,
        *,
        input_key: str = "input",
        history_key: str | None = "history",
        extras: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """LangChain Runnable 桥"""
        from chameleon.integrations.bridges import astream_from_runnable

        async for ev in astream_from_runnable(
            ctx,
            runnable,
            input_key=input_key,
            history_key=history_key,
            extras=extras,
        ):
            yield ev
