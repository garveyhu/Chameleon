"""advisor-demo —— 框架升级「全部新能力」演示智能体（一对一教学）。

这一个 @agent 用上了本次代码框架增强涉及到的所有新能力。平台隐式注入模型 / 知识库 /
工具 / 记忆 / 追踪 / 计费——作者只写下面这段业务逻辑，每种能力一行就接上：

  ① 语义记忆召回   ctx.memory.search()      —— 跨会话「记得你」（向量+BM25 hybrid，按身份隔离）
  ② 知识库 RAG     ctx.kb.search()          —— 有据可查（hybrid + 自动 citation 进 trace）
  ③ 带工具的生成   ctx.run_with_tools()     —— 会查会用工具（ReAct 循环）
       这一条调用「同时」自动享受：弹性重试(retries) + 入口防注入 + 出口 PII 脱敏 + 可重放(durable)
  ④ 人在环审批     ctx.ask_human()          —— 高风险动作暂停等你批准；断电/重启能从这续跑(durable)
  ⑤ 工作记忆       ctx.memory.update_working() —— 用户画像增量更新，下轮自动注入 system
  ⑥ 语义入库       ctx.memory.set()         —— 旁路 embedding 入库，下次能被①召回
  + 声明即生效：working_memory / observe_memory(长对话压缩) / guardrails / retries / durable
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from chameleon.agentkit import (
    AgentRun,
    ModelSlot,
    NoInjection,
    Opt,
    PiiRedact,
    agent,
    tool,
)


class CustomerProfile(BaseModel):
    """工作记忆的结构（跨会话记住的用户画像）。声明后每轮自动渲染进 system。"""

    name: str = ""  # 称呼
    tier: str = ""  # 会员等级
    preference: str = ""  # 偏好（如"只要简短回答"）


@tool(name="lookup_order", description="按订单号查订单的发货状态与预计送达")
async def lookup_order(order_no: str) -> dict:
    """一个本地工具示例——真实 agent 这里会查 DB / 调内部 API；演示返样例数据。"""
    return {"order_no": order_no, "status": "已发货", "eta": "明天 18:00 前送达"}


# 抓金额：必须带货币符号(¥/￥/$)或「元/块」语境，避免把订单号(A1001)误读成金额
_AMOUNT_RE = re.compile(r"(?:¥|￥|\$)\s*(\d{3,})|(\d{3,})\s*(?:元|块)")
_NAME_RE = re.compile(r"我(?:叫|是)\s*([一-龥A-Za-z]{1,8})")  # 抓自我介绍


@agent(
    key="advisor-demo",
    name="全能顾问助手（能力演示）",
    description="用上框架升级全部新能力的真实智能体：记忆 / 检索 / 工具 / 审批 / 弹性 / 安全",
    tags=["example", "showcase"],
    models=[ModelSlot("chat", "对话模型")],
    kb=True,  # 关联知识库 → ctx.kb.search 可用
    working_memory=CustomerProfile,  # 结构化工作记忆，自动注入
    observe_memory=True,  # 长对话后台 Observer→Reflector 压缩
    durable=True,  # 可恢复执行 + 人在环（ask_human）
    retries=2,  # ctx LLM 调用瞬时错误退避重试
    guardrails=[NoInjection(), PiiRedact(stage="output")],  # 安全轨道
    config=[Opt("approve_over", "需人工审批的金额阈值（元）", type="number", default=1000)],
)
async def handle(ctx: AgentRun):
    # ① 语义记忆召回：按本轮问题，跨会话回忆相关过往（向量+BM25 hybrid，按 end_user 身份隔离）
    recalled = await ctx.memory.search(ctx.query, top_k=3)
    memo = "；".join(m.text for m in recalled) if recalled else "（暂无相关记忆）"

    # ② 知识库 RAG：hybrid 检索 + 自动把命中的 citation 记进 trace（运营可溯源）
    docs = await ctx.kb.search(ctx.query, top_k=3)

    # ③ 带工具的生成：一条调用同时享受【弹性重试】+【入口防注入】+【出口 PII 脱敏】+【可重放】。
    #    平台还自动把 working memory（用户画像）+ observational（历史要点）注入 system，作者不用管。
    answer = ""
    async for chunk in ctx.run_with_tools(
        system=(
            "你是贴心专业的顾问。结合检索资料与该用户的已知画像/历史要点作答，回答简洁。"
            f"相关记忆：{memo}。"
        ),
        user=ctx.query,
        tools=[lookup_order],
        context=docs,
    ):
        answer += chunk

    # ④ 高风险动作 → 人在环审批（durable）：金额超阈值则暂停等人工批准；进程重启/恢复能从这续跑，
    #    且审批后的真实副作用重放不会被重复执行（journal 防决策翻转）。
    amt = _AMOUNT_RE.search(ctx.query)
    money = int(amt.group(1) or amt.group(2)) if amt else 0
    if money > int(ctx.config.get("approve_over", 1000)):
        decision = await ctx.ask_human(
            f"用户要操作金额 ¥{money}，超过审批阈值，是否批准？"
        )
        answer += f"\n\n【人工审批结果】{decision}"

    # ⑤ 增量更新工作记忆（下一轮自动注入 system，用户不必每次重新自我介绍）
    name = _NAME_RE.search(ctx.query)
    if name:
        await ctx.memory.update_working(name=name.group(1))

    # ⑥ 把这轮事实写进语义记忆（旁路 embedding 入向量集合，下次可被①语义召回）
    await ctx.memory.set(f"interaction:{ctx.session_id or 'anon'}", f"用户问：{ctx.query}")

    yield answer
