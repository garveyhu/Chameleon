"""Chameleon 本地智能体作者 SDK（公共面）。

作者只 import 这一处：

    from chameleon.agentkit import agent, AgentRun, ModelSlot, Opt

    @agent(
        key="kefu-faq", name="客服 FAQ",
        models=[ModelSlot("chat", "对话模型")], kb=True,
        config=[Opt("tone", "语气", choices=["专业", "活泼"], default="专业")],
    )
    async def handle(ctx: AgentRun) -> str:
        docs = await ctx.kb.search(ctx.query, top_k=3)
        return await ctx.complete(slot="chat", system="你是客服", context=docs, user=ctx.query)

模型 / KB 都来自平台「已配置资源池」，code/kb_key 会校验、非任填；web 是
降低简单 agent 门槛的便捷层、非必经——复杂 agent 可在代码里 `ctx.llm(model=...)`
/ `ctx.kb.search(kbs=[...])` 直接点名，完全不依赖前端（见设计文档 §3.1）。

本模块即冻结的公共 API；内部实现（routing / kb / observe / registry）一律私有、
可随意重构。破坏性变更走 major 版本。
"""

from chameleon.agentkit._decorator import agent, declared_agents
from chameleon.agentkit._runtime import AgentRun, KbHandle, RuntimeTransport
from chameleon.agentkit._spec import AgentManifest, Doc, ModelSlot, Opt

# 高级用法（有状态 / 多节点）+ 流事件类型：从既有包 re-export，
# 让作者只依赖 agentkit 一处。
from chameleon.core.base import AgentMetadata, BaseAgent
from chameleon.providers.base.types import Message, StreamEvent, StreamEventType

__all__ = [
    "AgentManifest",
    "AgentMetadata",
    "AgentRun",
    "BaseAgent",
    "Doc",
    "KbHandle",
    "Message",
    "ModelSlot",
    "Opt",
    "RuntimeTransport",
    "StreamEvent",
    "StreamEventType",
    "agent",
    "declared_agents",
]
