"""example-rag-qa —— 知识库问答：检索关联 KB → 注入上下文 → 模型作答。

展示：
- `kb=True`：页面"关联 KB"配的库会被 `ctx.kb.search` 自动检索，命中自动发引用。
- `models=[ModelSlot("chat")]`：作答模型槽，页面"关联模型"可绑任意已配置模型。
- `ctx.stream(context=docs)`：把检索结果作参考资料注入 prompt，流式作答 + 自动 trace。

未关联 KB 时 `ctx.kb.search` 返空，退化为直接作答（无引用）。
"""

from __future__ import annotations

from chameleon.agentkit import AgentRun, ModelSlot, agent

SYSTEM_PROMPT = (
    "你是知识库问答助手。优先依据「参考资料」回答；"
    "资料不足时如实说明，不要编造。回答用中文、简洁清晰。"
)


@agent(
    key="example-rag-qa",
    name="RAG 问答",
    description="检索关联知识库 + 模型作答（自动引用）",
    tags=["example", "rag", "kb"],
    models=[ModelSlot("chat", "问答模型")],
    kb=True,
)
async def handle(ctx: AgentRun):
    docs = await ctx.kb.search(ctx.query, top_k=5)
    async for delta in ctx.stream(
        slot="chat", system=SYSTEM_PROMPT, context=docs or None, user=ctx.query
    ):
        yield delta
