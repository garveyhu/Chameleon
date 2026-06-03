"""dashboard 聚合服务层（API 零业务逻辑，聚合全部下沉到此）

口径约束（两条铁律）：
1. 所有指标跟随调用方传入的 [range_from, range_to] 区间，不写死 24h/7d。
2. 所有聚合只算 trace 根行 `parent_id IS NULL`，与 call_logs 的 cost rollup 对齐——
   否则子 generation/span 行会被重复累加，导致 token/计数虚高。

id→可读名解析（display_name）见 resolve 模块。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.data.models import CallLog
from chameleon.system.dashboard import resolve, schemas

# 可聚合的维度列（通用 top-N / 成本下钻 / 分布 共用一张白名单）
DIMENSION_COLS = {
    "agent_key": CallLog.agent_key,
    "app_id": CallLog.app_id,
    "session_id": CallLog.session_id,
    "user_id": CallLog.user_id,
    "end_user_id": CallLog.end_user_id,
    "model_code": CallLog.model_code,
    "channel": CallLog.channel,
    "error_class": CallLog.error_class,
}


def _root():
    """trace 根行过滤：只算 parent_id IS NULL，避免子 span 重复累加。"""
    return CallLog.parent_id.is_(None)


def resolve_range(
    from_ts: datetime | None, to_ts: datetime | None, hours: int
) -> tuple[datetime, datetime]:
    """统一区间解析：from_ts/to_ts 优先，否则回退 now-hours。"""
    now = datetime.now(timezone.utc)
    if from_ts and to_ts:
        return from_ts, to_ts
    return now - timedelta(hours=hours), now


def _label(v: object) -> str:
    return str(v) if v is not None else "<空>"


async def get_overview(
    session: AsyncSession, rf: datetime, rt: datetime
) -> schemas.OverviewItem:
    """综合概览：区间口径 + 上一周期 delta，全部走 trace 根行。"""
    span = rt - rf
    prev_from, prev_to = rf - span, rf

    cur = (
        await session.execute(
            select(
                func.count(CallLog.id),
                func.count(CallLog.id).filter(CallLog.success.is_(True)),
                func.coalesce(func.avg(CallLog.duration_ms), 0.0),
                func.coalesce(func.sum(CallLog.prompt_tokens), 0),
                func.coalesce(func.sum(CallLog.completion_tokens), 0),
                func.count(func.distinct(CallLog.app_id)),
                func.count(func.distinct(CallLog.agent_key)),
                func.count(func.distinct(CallLog.end_user_id)),
                func.count(CallLog.id).filter(CallLog.stream.is_(True)),
                func.avg(CallLog.completion_start_ms),
            ).where(CallLog.created_at >= rf, CallLog.created_at <= rt, _root())
        )
    ).one()
    prev = (
        await session.execute(
            select(
                func.count(CallLog.id),
                func.count(CallLog.id).filter(CallLog.success.is_(True)),
            ).where(
                CallLog.created_at >= prev_from,
                CallLog.created_at < prev_to,
                _root(),
            )
        )
    ).one()

    total = int(cur[0] or 0)
    success = int(cur[1] or 0)
    prompt_tokens = int(cur[3] or 0)
    completion_tokens = int(cur[4] or 0)
    stream_calls = int(cur[8] or 0)
    prev_total = int(prev[0] or 0)
    prev_success = int(prev[1] or 0)

    # P95 响应延迟：percentile_cont 仅 PG 支持，SQLite（测试库）降级为 None
    p95_dur = None
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        p95_dur = (
            await session.execute(
                select(
                    func.percentile_cont(0.95).within_group(CallLog.duration_ms.asc())
                ).where(CallLog.created_at >= rf, CallLog.created_at <= rt, _root())
            )
        ).scalar_one()

    return schemas.OverviewItem(
        range_from=rf,
        range_to=rt,
        total_calls=total,
        prev_period_calls=prev_total,
        success_rate=(success / total) if total else 1.0,
        prev_success_rate=(prev_success / prev_total) if prev_total else None,
        avg_duration_ms=float(cur[2] or 0),
        total_prompt_tokens=prompt_tokens,
        total_completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        active_apps=int(cur[5] or 0),
        active_agents=int(cur[6] or 0),
        active_end_users=int(cur[7] or 0),
        stream_ratio=(stream_calls / total) if total else 0.0,
        p95_duration_ms=float(p95_dur) if p95_dur is not None else None,
        ttft_avg_ms=float(cur[9]) if cur[9] is not None else None,
    )


async def get_timeseries(
    session: AsyncSession, rf: datetime, rt: datetime, granularity: str
) -> schemas.TimeSeriesResult:
    """调用/错误时序，按 hour/day 分桶（granularity=auto 时按区间长度自选）。"""
    if granularity == "auto":
        span_hours = (rt - rf).total_seconds() / 3600
        granularity = "hour" if span_hours <= 48 else "day"
    bucket = func.date_trunc(granularity, CallLog.created_at).label("bucket")
    rows = (
        await session.execute(
            select(
                bucket,
                func.count(CallLog.id).label("total"),
                func.count(CallLog.id)
                .filter(CallLog.success.is_(False))
                .label("errors"),
            )
            .where(CallLog.created_at >= rf, CallLog.created_at <= rt, _root())
            .group_by(bucket)
            .order_by(bucket)
        )
    ).all()
    return schemas.TimeSeriesResult(
        granularity=granularity,
        points=[
            schemas.TimePoint(ts=r.bucket, total=r.total, errors=r.errors) for r in rows
        ],
    )


async def get_top_dimension(
    session: AsyncSession,
    rf: datetime,
    rt: datetime,
    dimension: str,
    limit: int,
) -> list[schemas.TopDimensionRow]:
    """通用维度 top-N（按调用量），替代 top-agents/top-apps 两个单维端点。"""
    col = DIMENSION_COLS[dimension]
    rows = (
        await session.execute(
            select(col.label("label"), func.count(CallLog.id).label("cnt"))
            .where(CallLog.created_at >= rf, CallLog.created_at <= rt, _root())
            .group_by(col)
            .order_by(func.count(CallLog.id).desc())
            .limit(limit)
        )
    ).all()
    base = [
        schemas.TopDimensionRow(label=_label(r.label), count=int(r.cnt or 0))
        for r in rows
    ]
    names = await resolve.resolve_names(session, dimension, [b.label for b in base])
    for b in base:
        b.display_name = names.get(b.label)
    return base


async def get_cost_totals(
    session: AsyncSession, rf: datetime, rt: datetime
) -> schemas.CostTotalsResult:
    """成本卡片：区间总成本 + 总 token + 上一周期 delta。"""
    span = rt - rf
    prev_from, prev_to = rf - span, rf

    cur = (
        await session.execute(
            select(
                func.coalesce(func.sum(CallLog.cost_usd), 0),
                func.count(CallLog.id),
                func.coalesce(func.sum(CallLog.prompt_tokens), 0),
                func.coalesce(func.sum(CallLog.completion_tokens), 0),
            ).where(CallLog.created_at >= rf, CallLog.created_at <= rt, _root())
        )
    ).one()
    prev_usd = float(
        (
            await session.execute(
                select(func.coalesce(func.sum(CallLog.cost_usd), 0)).where(
                    CallLog.created_at >= prev_from,
                    CallLog.created_at <= prev_to,
                    _root(),
                )
            )
        ).scalar_one()
        or 0
    )

    total_usd = float(cur[0] or 0)
    delta_pct = (total_usd - prev_usd) / prev_usd * 100.0 if prev_usd > 0 else None
    return schemas.CostTotalsResult(
        range_from=rf,
        range_to=rt,
        total_usd=total_usd,
        prev_total_usd=prev_usd if prev_usd > 0 else None,
        delta_pct=delta_pct,
        total_calls=int(cur[1] or 0),
        total_tokens=int((cur[2] or 0) + (cur[3] or 0)),
    )


async def get_cost_by_dimension(
    session: AsyncSession,
    rf: datetime,
    rt: datetime,
    dimension: str,
    limit: int,
) -> list[schemas.CostDimensionRow]:
    """按维度聚合成本 top-N，附带成功调用数 + token（前端算成功率/单价）。"""
    col = DIMENSION_COLS[dimension]
    rows = (
        await session.execute(
            select(
                col.label("label"),
                func.coalesce(func.sum(CallLog.cost_usd), 0).label("cost"),
                func.count(CallLog.id).label("cnt"),
                func.count(CallLog.id).filter(CallLog.success.is_(True)).label("ok"),
                func.coalesce(func.sum(CallLog.prompt_tokens), 0).label("pt"),
                func.coalesce(func.sum(CallLog.completion_tokens), 0).label("ct"),
            )
            .where(CallLog.created_at >= rf, CallLog.created_at <= rt, _root())
            .group_by(col)
            .order_by(func.sum(CallLog.cost_usd).desc().nullslast())
            .limit(limit)
        )
    ).all()
    base = [
        schemas.CostDimensionRow(
            label=_label(r.label),
            cost_usd=float(r.cost or 0),
            calls=int(r.cnt or 0),
            success_calls=int(r.ok or 0),
            total_tokens=int((r.pt or 0) + (r.ct or 0)),
        )
        for r in rows
    ]
    names = await resolve.resolve_names(session, dimension, [b.label for b in base])
    for b in base:
        b.display_name = names.get(b.label)
    return base


async def get_cost_timeseries(
    session: AsyncSession, rf: datetime, rt: datetime, bucket: str
) -> list[schemas.CostTimeseriesPoint]:
    """成本时序，按 hour/day 分桶。"""
    trunc = func.date_trunc(bucket, CallLog.created_at).label("ts")
    rows = (
        await session.execute(
            select(
                trunc,
                func.coalesce(func.sum(CallLog.cost_usd), 0).label("cost"),
                func.coalesce(func.sum(CallLog.prompt_tokens), 0).label("pt"),
                func.coalesce(func.sum(CallLog.completion_tokens), 0).label("ct"),
            )
            .where(CallLog.created_at >= rf, CallLog.created_at <= rt, _root())
            .group_by(trunc)
            .order_by(trunc.asc())
        )
    ).all()
    return [
        schemas.CostTimeseriesPoint(
            ts=r.ts,
            cost_usd=float(r.cost or 0),
            total_tokens=int((r.pt or 0) + (r.ct or 0)),
        )
        for r in rows
    ]


async def get_distribution(
    session: AsyncSession,
    rf: datetime,
    rt: datetime,
    dimension: str,
    limit: int,
) -> list[schemas.DistributionRow]:
    """单维分布 top-N（调用数 + 成本）。error_class 维度只统计失败行。"""
    col = DIMENSION_COLS[dimension]
    where = [CallLog.created_at >= rf, CallLog.created_at <= rt, _root()]
    if dimension == "error_class":
        where.append(CallLog.success.is_(False))
    rows = (
        await session.execute(
            select(
                col.label("label"),
                func.count(CallLog.id).label("cnt"),
                func.coalesce(func.sum(CallLog.cost_usd), 0).label("cost"),
            )
            .where(*where)
            .group_by(col)
            .order_by(func.count(CallLog.id).desc())
            .limit(limit)
        )
    ).all()
    base = [
        schemas.DistributionRow(
            label=_label(r.label),
            count=int(r.cnt or 0),
            cost_usd=float(r.cost or 0),
        )
        for r in rows
    ]
    names = await resolve.resolve_names(session, dimension, [b.label for b in base])
    for b in base:
        b.display_name = names.get(b.label)
    return base
