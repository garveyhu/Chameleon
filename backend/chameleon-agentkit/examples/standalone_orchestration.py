"""脱平台多智能体编排示例 —— 装好内部 SDK + langchain-openai 后直接跑（本机自测）。

演示 agentkit 的差异化卖点：**多智能体编排就是普通 Python 代码 + ctx 原语**，不需画图、不需
学 DSL。这里一个"辩论主持"agent 用 `ctx.gather` 并行扇出到正/反两个专家子 agent，再综合两方
观点。子 agent 在 standalone 下走本地注册表（`StandaloneTransport(agents=...)`）；提交平台后
同一份代码走进程内 A2A（深度/预算/trace 自动守），零改动。

运行（需自带 OpenAI key，或换任意 LangChain chat model）：
    export OPENAI_API_KEY=sk-...
    python standalone_orchestration.py
"""

from __future__ import annotations

import asyncio

from chameleon.agentkit import AgentRun, ModelSlot, agent
from chameleon.agentkit.standalone import StandaloneTransport, run_standalone


@agent(key="pros-bot", name="正方", models=[ModelSlot("chat", "对话")])
async def pros(ctx: AgentRun):
    yield await ctx.complete(system="你是正方，只列支持该议题的有力理由，简洁。", user=ctx.query)


@agent(key="cons-bot", name="反方", models=[ModelSlot("chat", "对话")])
async def cons(ctx: AgentRun):
    yield await ctx.complete(system="你是反方，只列反对该议题的有力理由，简洁。", user=ctx.query)


@agent(
    key="debate-host",
    name="辩论主持",
    description="并行问正反两方专家，综合呈现（多智能体编排）",
    models=[ModelSlot("chat", "对话")],
    call_agents=["pros-bot", "cons-bot"],  # A2A allow-list（沙箱下据此 scope）
)
async def debate(ctx: AgentRun):
    # 一行并行扇出到两个子 agent（map-reduce）；预算/trace/深度红线由框架守
    pros_view, cons_view = await ctx.gather(
        [("pros-bot", ctx.query), ("cons-bot", ctx.query)]
    )
    yield f"【议题】{ctx.query}\n\n【正方】\n{pros_view}\n\n【反方】\n{cons_view}"


async def main() -> None:
    from langchain_openai import ChatOpenAI

    transport = StandaloneTransport(
        model=ChatOpenAI(model="gpt-4o-mini", temperature=0),
        agents={"pros-bot": pros, "cons-bot": cons},  # 本地子 agent 注册表
    )
    print(await run_standalone(debate, "公司是否该全面远程办公", transport=transport))


if __name__ == "__main__":
    asyncio.run(main())
