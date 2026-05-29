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
from chameleon.core.models import (
    Agent,
    ApiKey,
    CallLog,
    ChatSession,
    Graph,
    Message,
    Score,
)
from chameleon.core.observe import aggregate_rollups
from chameleon.providers.base import PROVIDERS
from chameleon.system.admin.schemas import (
    CallLogDetailItem,
    CallLogItem,
    ProviderStatusItem,
    SessionItem,
    TraceTreeNode,
)
from chameleon.system.scores.schemas import ScoreItem

_INPUT_PREVIEW_KEYS = ["question", "input", "query", "text", "prompt_preview"]
_OUTPUT_PREVIEW_KEYS = ["output", "answer", "text", "output_preview"]


def _payload_preview(
    payload: dict | None, keys: list[str], max_len: int = 160
) -> str | None:
    """从根行 payload 抽一段短文本预览（命中 keys；否则取 messages 末条 content）。"""
    if not isinstance(payload, dict):
        return None
    for k in keys:
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()[:max_len]
    msgs = payload.get("messages")
    if isinstance(msgs, list):
        for m in reversed(msgs):
            if isinstance(m, dict) and isinstance(m.get("content"), str):
                c = m["content"].strip()
                if c:
                    return c[:max_len]
    return None


async def list_call_logs(
    session: AsyncSession,
    page: PageParams,
    *,
    app_id: str | None = None,
    agent_key: str | None = None,
    channel: str | None = None,
    model_code: str | None = None,
    session_id: str | None = None,
    end_user_id: str | None = None,
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
            ChatSession.title.label("session_title"),
        )
        .select_from(CallLog)
        .outerjoin(ApiKey, ApiKey.id == CallLog.api_key_id)
        .outerjoin(Agent, Agent.agent_key == CallLog.agent_key)
        .outerjoin(Graph, Graph.id == Agent.graph_id)
        .outerjoin(ChatSession, ChatSession.session_id == CallLog.session_id)
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
    if end_user_id is not None:
        stmt = stmt.where(CallLog.end_user_id == end_user_id)
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
        item.session_title = row.session_title
        item.input_preview = _payload_preview(log.request_payload, _INPUT_PREVIEW_KEYS)
        item.output_preview = _payload_preview(log.response_payload, _OUTPUT_PREVIEW_KEYS)
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


async def list_sessions(
    session: AsyncSession,
    page: PageParams,
    *,
    agent_key: str | None = None,
    end_user_id: str | None = None,
    channel: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> PageResult[SessionItem]:
    """会话（thread）列表 —— 按 ChatSession 维度（多轮对话一条），区别于 trace 列表。

    turn_count 子查询 SUM messages；channel 由 call_logs 根行派生（一会话渠道一致）；
    按 last_message_at（无则 created_at）倒序。
    """
    turn_sq = (
        select(Message.session_id, func.count(Message.id).label("cnt"))
        .group_by(Message.session_id)
        .subquery()
    )
    # 渠道派生：取该会话 trace 根行的 channel（同一会话渠道一致，聚合任取其一）
    chan_sq = (
        select(CallLog.session_id, func.max(CallLog.channel).label("channel"))
        .where(CallLog.parent_id.is_(None), CallLog.session_id.is_not(None))
        .group_by(CallLog.session_id)
        .subquery()
    )
    base = (
        select(ChatSession, turn_sq.c.cnt, chan_sq.c.channel)
        .outerjoin(turn_sq, turn_sq.c.session_id == ChatSession.session_id)
        .outerjoin(chan_sq, chan_sq.c.session_id == ChatSession.session_id)
        .where(ChatSession.deleted_at.is_(None))
    )
    if agent_key:
        base = base.where(ChatSession.agent_key == agent_key)
    if end_user_id:
        base = base.where(ChatSession.end_user_id == end_user_id)
    if channel:
        base = base.where(chan_sq.c.channel == channel)
    if since:
        base = base.where(ChatSession.created_at >= since)
    if until:
        base = base.where(ChatSession.created_at <= until)

    total = (
        await session.execute(
            select(func.count()).select_from(base.subquery())
        )
    ).scalar_one()

    order_col = func.coalesce(ChatSession.last_message_at, ChatSession.created_at)
    rows = (
        await session.execute(
            base.order_by(order_col.desc())
            .offset((page.page - 1) * page.page_size)
            .limit(page.page_size)
        )
    ).all()

    items = [
        SessionItem(
            id=cs.id,
            session_id=cs.session_id,
            agent_key=cs.agent_key,
            app_id=cs.app_id,
            end_user_id=cs.end_user_id,
            channel=chan,
            title=cs.title,
            turn_count=cnt or 0,
            last_message_at=cs.last_message_at,
            created_at=cs.created_at,
        )
        for cs, cnt, chan in rows
    ]
    return PageResult(items=items, total=total, page=page.page, page_size=page.page_size)


async def providers_status() -> list[ProviderStatusItem]:
    items: list[ProviderStatusItem] = []
    for name, provider in PROVIDERS.items():
        try:
            ok = await provider.healthcheck()
            items.append(ProviderStatusItem(name=name, ok=bool(ok)))
        except Exception as e:  # noqa: BLE001
            items.append(ProviderStatusItem(name=name, ok=False, error=str(e)))
    return items
