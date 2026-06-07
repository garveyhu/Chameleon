"""example-tool-use —— 工具调用：本地 @tool + 平台工具混用，自动 ReAct 循环。

展示编码智能体的核心能力——工具调用（配置双源、代码优先）：
- 本地 `@tool`：作者在代码里直接定义工具函数（calc），随 agent 代码走、不入平台
  registry。最贴「代码优先」哲学。
- 平台工具：`@agent(tools=["http"])` 点名平台 registry 已注册工具，web「关联工具」
  可启停。
- `ctx.run_with_tools(...)`：自动 ReAct 循环——模型出 tool_call → 执行（本地走
  handler / 平台走 registry）→ 回填 → 续轮 → 出最终答案。工具调用 / 结果自动 emit
  成 tool_call / tool_result 事件 + trace + usage 累加，作者零样板。
"""

from __future__ import annotations

from chameleon.agentkit import AgentRun, ModelSlot, Opt, agent, tool

SYSTEM_PROMPT = (
    "你是带工具的助手。遇到需要计算或查询外部信息时，调用相应工具，"
    "拿到结果后用中文简洁作答；不要编造工具能给出的事实。"
)


@tool(name="calc", description="计算一个算术表达式，返回数值结果")
async def calc(expression: str) -> dict:
    """安全求值一个仅含数字与 + - * / ( ) . 的算术表达式。"""
    allowed = set("0123456789+-*/(). ")
    if not expression or set(expression) - allowed:
        return {"error": "表达式只能包含数字与 + - * / ( ) ."}
    try:
        value = eval(expression, {"__builtins__": {}}, {})  # noqa: S307  受限字符集
    except Exception as e:  # noqa: BLE001
        return {"error": f"无法计算: {e}"}
    return {"expression": expression, "value": value}


@agent(
    key="example-tool-use",
    name="工具调用助手",
    description="本地 @tool + 平台工具混用（ReAct 循环）",
    tags=["example", "tools", "react"],
    models=[ModelSlot("chat", "对话模型")],
    tools=["http"],  # 平台工具点名；web「关联工具」可启停
    config=[Opt("max_steps", "工具循环上限", type="number", default=6)],
)
async def handle(ctx: AgentRun):
    max_steps = int(ctx.config.get("max_steps") or 6)
    async for delta in ctx.run_with_tools(
        slot="chat",
        system=SYSTEM_PROMPT,
        user=ctx.query,
        tools=[calc],  # 本地工具；平台 http 来自 @agent(tools=)
        max_steps=max_steps,
    ):
        yield delta
