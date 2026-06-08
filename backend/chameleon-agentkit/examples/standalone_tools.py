"""脱平台工具调用（ReAct）示例 —— `pip install chameleon-agentkit langchain-openai` 后直接跑。

演示带工具的智能体：声明本地 `@tool`，`ctx.run_with_tools` 自动跑 ReAct 循环（模型出 tool_calls
→ 框架执行你的工具 → 回填续跑 → 出最终答案）。本地工具随代码走，无需任何平台配置；提交平台后
平台工具（http/sql 等）也能经 `@agent(tools=[...])` 混用。

运行（需自带 OpenAI key，或换任意支持 tool calling 的 LangChain chat model）：
    export OPENAI_API_KEY=sk-...
    python standalone_tools.py
"""

from __future__ import annotations

import asyncio

from chameleon.agentkit import AgentRun, ModelSlot, agent, tool
from chameleon.agentkit.standalone import StandaloneTransport, run_standalone


@tool(name="add", description="计算两个整数之和")
async def add(a: int, b: int) -> int:
    return a + b


@tool(name="now_year", description="返回当前年份")
async def now_year() -> int:
    return 2026


@agent(key="calc-bot", name="计算助手", models=[ModelSlot("chat", "对话")])
async def handle(ctx: AgentRun):
    # ReAct：模型按需调用 add / now_year，框架执行后回填，循环到出最终答案
    async for delta in ctx.run_with_tools(
        system="你是助手，需要算数时调用工具，不要心算。",
        user=ctx.query,
        tools=[add, now_year],
        max_steps=4,
    ):
        yield delta


async def main() -> None:
    from langchain_openai import ChatOpenAI

    transport = StandaloneTransport(model=ChatOpenAI(model="gpt-4o-mini", temperature=0))
    print(await run_standalone(handle, "今年加上 17 是多少？", transport=transport))


if __name__ == "__main__":
    asyncio.run(main())
