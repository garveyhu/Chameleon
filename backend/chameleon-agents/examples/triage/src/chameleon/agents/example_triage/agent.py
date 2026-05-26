"""example-triage —— 分诊问答：先用小模型判意图类型，再用对话模型作答。

展示进阶组合：
- 两个**具名模型槽**：`fast`（判类，便宜快）+ `chat`（作答）。页面"关联模型"可分别绑
  不同模型，运行时 `ctx.complete(slot="fast")` / `ctx.stream(slot="chat")` 各取所需。
- `config=[Opt(...)]`：运营可在页面调"回答风格"，进 `ctx.config`。
- 一次非流式 `ctx.complete` + 一次流式 `ctx.stream`，都自动 trace。
"""

from __future__ import annotations

from chameleon.agentkit import AgentRun, ModelSlot, Opt, agent


@agent(
    key="example-triage",
    name="分诊问答",
    description="小模型判意图 + 对话模型作答（多模型槽 + 运营配置）",
    tags=["example", "router", "multi-model"],
    models=[
        ModelSlot("fast", "意图分类小模型"),
        ModelSlot("chat", "作答模型"),
    ],
    config=[
        Opt("style", "回答风格", type="select", choices=["简洁", "详细"], default="简洁"),
    ],
)
async def handle(ctx: AgentRun):
    kind = await ctx.complete(
        slot="fast",
        system="判断用户意图属于：闲聊 / 技术 / 投诉。只回类别词，不要任何多余内容。",
        user=ctx.query,
    )
    style = ctx.config.get("style") or "简洁"
    system = f"你是分诊助手，用户意图类别约为「{kind.strip()}」。请用「{style}」风格作答，中文。"
    async for delta in ctx.stream(slot="chat", system=system, user=ctx.query):
        yield delta
