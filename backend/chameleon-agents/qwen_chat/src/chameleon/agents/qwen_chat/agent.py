"""qwen-chat —— 通用聊天 agent（agentkit @agent 范式样板）。

最小完整范式：只写业务逻辑，模型从 ctx 隐式拿。
- `models=[ModelSlot("chat")]`：声明一个对话模型槽；页面"关联模型"可绑任意已配置
  模型，未绑则用槽默认 / 系统默认。
- `ctx.stream(slot="chat", ...)`：自动用该槽解析出的模型，流式出文本、自动 trace。

作者不 import llm()、不传 agent_key、不手写 trace。
"""

from __future__ import annotations

from chameleon.agentkit import AgentRun, ModelSlot, agent

SYSTEM_PROMPT = """你是 Chameleon 的通用聊天助手。
要点：回答简洁、自然、有用；尽量用中文；适当使用 Markdown 格式。"""


@agent(
    key="qwen-chat",
    name="通用聊天",
    description="对接平台已配置的对话模型（关联模型未配=系统默认）",
    tags=["builtin", "chat", "qwen"],
    models=[ModelSlot("chat", "对话模型")],
)
async def handle(ctx: AgentRun):
    async for delta in ctx.stream(slot="chat", system=SYSTEM_PROMPT, user=ctx.query):
        yield delta
