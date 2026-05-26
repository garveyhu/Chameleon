"""qwen-chat —— 通用聊天 agent（agentkit @agent 范式样板）。

最小完整范式：只写业务逻辑，模型 / 知识库 / trace 从 ctx 隐式拿。
- `models=[ModelSlot("chat")]`：声明对话模型槽；页面"关联模型"可绑任意已配置模型。
- `kb=True`：声明用知识库；页面"关联 KB"配的库会被 `ctx.kb.search` 自动检索 + 引用。
- `ctx.kb.search(...)`：未关联 KB 时返空，退化为纯聊天；关联后自动检索 + 发 citation。
- `ctx.stream(slot=..., context=docs, ...)`：自动用该槽模型，把检索结果作参考资料，
  流式出文本、自动 trace。

作者不 import llm()/search_kb()、不传 agent_key、不手写 trace。
"""

from __future__ import annotations

from chameleon.agentkit import AgentRun, ModelSlot, agent

SYSTEM_PROMPT = """你是 Chameleon 的通用聊天助手。
要点：回答简洁、自然、有用；尽量用中文；适当使用 Markdown 格式。
若提供了参考资料，优先据此回答。"""


@agent(
    key="qwen-chat",
    name="通用聊天",
    description="对接平台已配置的对话模型 + 可选知识库（关联后自动检索引用）",
    tags=["builtin", "chat", "qwen"],
    models=[ModelSlot("chat", "对话模型")],
    kb=True,
)
async def handle(ctx: AgentRun):
    docs = await ctx.kb.search(ctx.query, top_k=3)  # 未关联 KB → 空，退化为纯聊天
    async for delta in ctx.stream(
        slot="chat", system=SYSTEM_PROMPT, context=docs or None, user=ctx.query
    ):
        yield delta
