"""example-orchestrator —— 编排：把计算类任务委托给子智能体（A2A 演示）。

展示 `ctx.call_agent`：本 agent 不自己算，转交给 example-tool-use（带工具的子智能体）
处理，再把结果包装返回。trace 不断链 / 预算 / 嵌套深度等红线由底层 engine a2a 统一守，
作者一行 `await ctx.call_agent(target, input=...)`。
"""

from __future__ import annotations

from chameleon.agentkit import AgentRun, ModelSlot, agent


@agent(
    key="example-orchestrator",
    name="编排助手",
    description="把计算任务委托给子智能体 example-tool-use（A2A 演示）",
    tags=["example", "a2a", "orchestrator"],
    models=[ModelSlot("chat", "对话模型")],
    # A2A allow-list：声明可调的子 agent（沙箱执行下据此 scope；进程内不强制）
    call_agents=["example-tool-use"],
)
async def handle(ctx: AgentRun):
    sub_answer = await ctx.call_agent("example-tool-use", input=ctx.query)
    yield f"已委托子智能体处理，结果：{sub_answer}"
