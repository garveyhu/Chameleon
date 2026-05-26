"""example-echo —— 最小 @agent 范式：纯函数 + ctx，零模型 / 零 KB / 零配置。

展示 agentkit 的最小书写面：一个 async 函数，从 ctx 拿输入、yield 文本增量即可。
框架完全解耦——不依赖 LLM / LangChain / LangGraph。
"""

from __future__ import annotations

from chameleon.agentkit import AgentRun, agent


@agent(
    key="example-echo",
    name="Echo（极简）",
    description="最小 @agent 范式：纯函数回声，零模型 / KB / 配置",
    tags=["example", "minimal"],
)
async def handle(ctx: AgentRun):
    yield f"echo: {ctx.query}"
