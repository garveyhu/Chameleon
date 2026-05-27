"""admin 业务服务

- list_call_logs：四维过滤（app/agent/时间窗/状态）
- providers_status：遍历 PROVIDERS 调 healthcheck（不缓存，v1 简版）
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.api.response import PageParams, PageResult
from chameleon.core.models import Agent, ApiKey, CallLog, Graph, Score
from chameleon.core.observe import aggregate_rollups
from chameleon.providers.base import PROVIDERS
from chameleon.system.admin.schemas import (
    CallLogDetailItem,
    CallLogItem,
    ProviderStatusItem,
    TraceTreeNode,
)
from chameleon.system.scores.schemas import ScoreItem


async def list_call_logs(
    session: AsyncSession,
    page: PageParams,
    *,
    app_id: str | None = None,
    agent_key: str | None = None,
    channel: str | None = None,
    model_code: str | None = None,
    session_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    success: bool | None = None,
) -> PageResult[CallLogItem]:
    """会话 & 运行账本列表（只列 trace 根 parent_id IS NULL）。

    join 推导每行的归属与编排方式，避免前端二次请求：
      - api_keys：api_key_id → 展示名
      - agents：agent_key → source（local / graph / dify / fastgpt / …）
      - graphs：source='graph' 时 agents.graph_id → graphs.kind（chatflow / workflow）

    子 span（tool_rounds / branch_runs / 节点观测）是内部嵌套，在详情页的
    树 / 甘特里看，不作独立行刷屏。
    """
    # left join 推导列；agents 按 agent_key 关联，graphs 再按 agent.graph_id 关联
    stmt = (
        select(
            CallLog,
            ApiKey.name.label("api_key_name"),
            Agent.source.label("source"),
            Graph.kind.label("kind"),
        )
        .select_from(CallLog)
        .outerjoin(ApiKey, ApiKey.id == CallLog.api_key_id)
        .outerjoin(Agent, Agent.agent_key == CallLog.agent_key)
        .outerjoin(Graph, Graph.id == Agent.graph_id)
        .where(CallLog.parent_id.is_(None))
    )
    if app_id is not None:
        stmt = stmt.where(CallLog.app_id == app_id)
    if agent_key is not None:
        stmt = stmt.where(CallLog.agent_key == agent_key)
    if channel is not None:
        stmt = stmt.where(CallLog.channel == channel)
    if model_code is not None:
        stmt = stmt.where(CallLog.model_code == model_code)
    if session_id is not None:
        stmt = stmt.where(CallLog.session_id == session_id)
    if since is not None:
        stmt = stmt.where(CallLog.created_at >= since)
    if until is not None:
        stmt = stmt.where(CallLog.created_at <= until)
    if success is not None:
        stmt = stmt.where(CallLog.success.is_(success))

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()

    rows = (
        await session.execute(
            stmt.order_by(CallLog.created_at.desc())
            .offset(page.offset)
            .limit(page.limit)
        )
    ).all()

    items: list[CallLogItem] = []
    for row in rows:
        log: CallLog = row[0]
        item = CallLogItem.model_validate(log)
        item.api_key_name = row.api_key_name
        item.source = row.source
        # kind 仅对 source='graph' 有意义（编排工作流）；其余 source 置空
        item.kind = row.kind if row.source == "graph" else None
        items.append(item)

    return PageResult(
        items=items,
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


async def get_call_log(
    session: AsyncSession, call_log_id: int
) -> CallLogDetailItem:
    row = (
        await session.execute(select(CallLog).where(CallLog.id == call_log_id))
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.Fail, message=f"call_log 不存在: {call_log_id}"
        )
    return CallLogDetailItem.model_validate(row)


async def get_trace_tree(
    session: AsyncSession, trace_request_id: str
) -> TraceTreeNode:
    """以 trace_request_id 为根，递归收集所有子 observation 拼成树

    实现：先查根 + 其所有后代（按 parent_id 链路 BFS）一次性 fetch，再 in-memory
    组装成树。这避免 N+1，对常见 trace 深度（< 50 节点）足够快。
    """
    root = (
        await session.execute(
            select(CallLog).where(CallLog.request_id == trace_request_id)
        )
    ).scalar_one_or_none()
    if root is None:
        raise BusinessError(
            ResultCode.Fail,
            message=f"call_log 不存在: request_id={trace_request_id}",
        )

    # BFS 收集所有后代 —— PG WITH RECURSIVE 也行但 ORM 麻烦；先 Python 层 BFS。
    # 假设单 trace 节点数不超过 ~500（绝大多数 trace 几十节点）。
    all_logs: dict[str, CallLog] = {root.request_id: root}
    frontier: list[str] = [root.request_id]
    safety = 0
    while frontier and safety < 20:  # 深度上限保护
        safety += 1
        children = (
            (
                await session.execute(
                    select(CallLog).where(CallLog.parent_id.in_(frontier))
                )
            )
            .scalars()
            .all()
        )
        next_frontier: list[str] = []
        for c in children:
            if c.request_id in all_logs:
                continue  # 防御性去重（循环指向理论上不该发生）
            all_logs[c.request_id] = c
            next_frontier.append(c.request_id)
        frontier = next_frontier

    # 一次性把树上所有 score 拉回来按 call_log_id 分桶
    score_rows = (
        (
            await session.execute(
                select(Score).where(Score.call_log_id.in_(all_logs.keys()))
            )
        )
        .scalars()
        .all()
    )
    scores_by_rid: dict[str, list[ScoreItem]] = {}
    for s in score_rows:
        scores_by_rid.setdefault(s.call_log_id, []).append(
            ScoreItem.model_validate(s)
        )

    # P23.C2 subtree cost / token 累加（含自身 + 所有后代）
    rollups = aggregate_rollups(all_logs.values())

    # 组装树
    def to_node(row: CallLog) -> TraceTreeNode:
        node = TraceTreeNode.model_validate(row)
        node.scores = scores_by_rid.get(row.request_id, [])
        rollup = rollups.get(row.request_id)
        if rollup is not None:
            node.rollup_cost_usd = (
                float(rollup.cost_usd) if rollup.cost_usd is not None else None
            )
            node.rollup_prompt_tokens = rollup.prompt_tokens
            node.rollup_completion_tokens = rollup.completion_tokens
            node.rollup_total_tokens = rollup.total_tokens
        return node

    nodes: dict[str, TraceTreeNode] = {
        rid: to_node(row) for rid, row in all_logs.items()
    }
    for rid, row in all_logs.items():
        if row.parent_id and row.parent_id in nodes:
            nodes[row.parent_id].children.append(nodes[rid])

    # children 按 created_at 升序排列
    for n in nodes.values():
        n.children.sort(key=lambda x: x.created_at)

    return nodes[root.request_id]


async def providers_status() -> list[ProviderStatusItem]:
    items: list[ProviderStatusItem] = []
    for name, provider in PROVIDERS.items():
        try:
            ok = await provider.healthcheck()
            items.append(ProviderStatusItem(name=name, ok=bool(ok)))
        except Exception as e:  # noqa: BLE001
            items.append(ProviderStatusItem(name=name, ok=False, error=str(e)))
    return items
