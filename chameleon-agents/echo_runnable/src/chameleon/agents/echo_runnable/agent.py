"""EchoRunnableAgent —— 用 LangChain Runnable 写 agent 的样板

不依赖 LangGraph。astream 走 from_runnable 桥。
不调真实 LLM（避免依赖 API key）；用 RunnableLambda 模拟 LLM 行为。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from langchain_core.messages import AIMessageChunk
from langchain_core.runnables import RunnableLambda

from chameleon.core.base import AgentMetadata, BaseAgent
from chameleon.providers.base.types import InvokeContext, StreamEvent


class EchoRunnableAgent(BaseAgent):
    """LangChain Runnable / LCEL 范式"""

    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            id="echo-runnable",
            name="Echo (LangChain Runnable)",
            description="LangChain LCEL Runnable 范式样板",
            version="0.1",
            tags=["builtin", "demo", "langchain"],
        )

    @classmethod
    def build_runnable(cls):
        """构造一个 LCEL Runnable

        真实场景里这会是 `prompt | llm | parser`。
        这里用 RunnableLambda + 假 LLM 模拟流式输出，避免依赖 API key。
        """

        async def _fake_llm_astream(payload):
            """按 chunk yield AIMessageChunk（模拟 LLM 流）"""
            text = "echo(runnable): " + payload.get("input", "")
            for i in range(0, len(text), 2):
                yield AIMessageChunk(content=text[i : i + 2])

        # RunnableLambda 包一层让 .astream 调 _fake_llm_astream
        async def _runnable_fn(payload):
            chunks = []
            async for c in _fake_llm_astream(payload):
                chunks.append(c)
            # 合并所有 chunk 返完整消息（非流式调用时用）
            full = "".join(getattr(c, "content", "") for c in chunks)
            return AIMessageChunk(content=full)

        # 直接构造一个支持 astream 的 lambda：用 astream 钩子
        class _StreamableLambda:
            async def astream(self, payload, *_args, **_kwargs):
                async for c in _fake_llm_astream(payload):
                    yield c

            async def ainvoke(self, payload, *_args, **_kwargs):
                return await _runnable_fn(payload)

        return _StreamableLambda()

    @classmethod
    async def astream(cls, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        """走 from_runnable 桥，无需自己写翻译"""
        runnable = cls.build_runnable()
        async for ev in cls.from_runnable(
            ctx, runnable, input_key="input", history_key="history"
        ):
            yield ev


_ = RunnableLambda  # 保留 import 让 lint 不报"未使用"
