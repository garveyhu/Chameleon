"""示例：人在环（HITL）+ 可恢复执行（durable）。

`@agent(durable=True)` 开 memoization 重放；`ctx.ask_human` 暂停 run 等人工审批，恢复后
journal 重放已记录的 ctx 调用（complete 不重调模型）、续跑过暂停点。

平台 e2e：调用 → 在 ask_human 暂停（响应带 run_id + pending）→ 带 run_id+答案重调 → 续跑完成。
"""

from __future__ import annotations

from chameleon.agentkit import AgentRun, ModelSlot, agent


@agent(
    key="example-hitl",
    name="审批助手",
    description="ctx.ask_human 人在环：暂停等人工审批，恢复续跑（durable memoization 重放）",
    tags=["example", "hitl", "durable"],
    models=[ModelSlot("chat", "对话模型")],
    durable=True,
)
async def handle(ctx: AgentRun):
    # complete 首跑记进 journal；恢复重放时直接返记录值，不重调模型（省钱/不重复副作用）
    summary = await ctx.complete(
        system="用一句话复述用户要执行的操作，不要执行。", user=ctx.query
    )
    # 暂停点：无答案 → 落 pending + 抛 AgentPaused，本次流优雅结束等人工
    decision = await ctx.ask_human(f"请审批以下操作：{summary}（回复 同意 或 拒绝）")
    yield f"审批结果：{decision}——操作「{summary}」"
