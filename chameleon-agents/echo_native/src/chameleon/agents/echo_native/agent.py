"""EchoNativeAgent —— 范式样板：纯 Python async generator

零外部框架依赖（除 chameleon-core + providers-base）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from chameleon.core.base import AgentMetadata, BaseAgent
from chameleon.providers.base.types import InvokeContext, StreamEvent, StreamEventType


class EchoNativeAgent(BaseAgent):
    """纯 Python echo agent —— 不用 LangGraph、不用 LangChain"""

    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            id="echo-native",
            name="Echo (Native)",
            description="纯 Python 异步生成器范式：演示本地 agent 框架解耦能力",
            version="0.1",
            tags=["builtin", "demo", "native"],
        )

    @classmethod
    async def astream(cls, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        """直接 yield StreamEvent，框架不干涉"""
        # 取当前轮文本
        if isinstance(ctx.input, str):
            text = ctx.input
        else:
            text = ctx.input[-1].content if ctx.input else ""

        # 1) step：演示中间步骤
        yield StreamEvent(
            type=StreamEventType.step,
            data={"name": "prepare", "status": "success", "duration_ms": 1},
        )

        # 2) delta：按字符流出（实际应用里可能是 LLM token）
        prefix = "echo(native): "
        for ch in prefix + text:
            yield StreamEvent(type=StreamEventType.delta, data={"text": ch})

        # 3) metadata：演示 usage 自报（agent 自己产生 usage 指标）
        yield StreamEvent(
            type=StreamEventType.metadata,
            data={
                "usage": {
                    "prompt_tokens": len(text),
                    "completion_tokens": len(prefix + text),
                    "total_tokens": len(text) + len(prefix + text),
                }
            },
        )
