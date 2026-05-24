"""dashboard HTTP 路由 (/v1/admin/dashboard)

- overview：综合卡片数据（含上一周期 delta）
- timeseries：时序聚合（按 hour / day 分桶）
- top-agents / top-apps / top-models：top N 列表

时间区间：
  既支持 hours= 简单参数（向下兼容），也支持 from_ts / to_ts ISO datetime。
  两者都不传走 hours=24 默认。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.core.infra.db import get_session
from chameleon.core.models import App, CallLog
from chameleon.system.auth.dependencies import require_permission


def _resolve_range(
    from_ts: datetime | None, to_ts: datetime | None, hours: int
) -> tuple[datetime, datetime]:
    """统一区间解析。

    优先级：from_ts/to_ts > hours
    """
    now = datetime.now(timezone.utc)
    if from_ts and to_ts:
        return from_ts, to_ts
    return now - timedelta(hours=hours), now


# ── DTO ────────────────────────────────────────────────────


class OverviewItem(BaseModel):
    # 兼容旧字段名（前端 dashboard 还在用）
    total_calls_24h: int
    total_calls_7d: int
    success_rate_24h: float
    avg_duration_ms_24h: float
    total_prompt_tokens_24h: int
    total_completion_tokens_24h: int
    active_apps_24h: int
    active_agents_24h: int
    # 与所选时间区间相关的指标（新加）
    range_from: datetime | None = None
    range_to: datetime | None = None
    total_calls_in_range: int = 0
    prev_period_calls: int = 0  # 上一同长度周期，用于 delta


class TimePoint(BaseModel):
    ts: datetime
    total: int
    errors: int


class TimeSeriesResult(BaseModel):
    granularity: str
    points: list[TimePoint]


class TopAgent(BaseModel):
    agent_key: str
    count: int


class TopApp(BaseModel):
    app_id: str
    count: int


# ── 路由 ──────────────────────────────────────────────────


router = APIRouter(prefix="/v1/admin/dashboard", tags=["admin:dashboard"])


@router.get("/overview", response_model=Result[OverviewItem])
async def overview(
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("dashboard:read")),
) -> Result[OverviewItem]:
    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)

    # 用户选定的时间区间（默认 24h）
    range_from, range_to = _resolve_range(from_ts, to_ts, hours=24)
    span = range_to - range_from
    prev_from = range_from - span
    prev_to = range_from

    total_24h = (
        await session.execute(
            select(func.count(CallLog.id)).where(CallLog.created_at >= since_24h)
        )
    ).scalar_one()
    total_7d = (
        await session.execute(
            select(func.count(CallLog.id)).where(CallLog.created_at >= since_7d)
        )
    ).scalar_one()
    success_24h = (
        await session.execute(
            select(func.count(CallLog.id)).where(
                CallLog.created_at >= since_24h, CallLog.success.is_(True)
            )
        )
    ).scalar_one()
    avg_dur = (
        await session.execute(
            select(func.coalesce(func.avg(CallLog.duration_ms), 0.0)).where(
                CallLog.created_at >= since_24h
            )
        )
    ).scalar_one()
    prompt_tokens = (
        await session.execute(
            select(func.coalesce(func.sum(CallLog.prompt_tokens), 0)).where(
                CallLog.created_at >= since_24h
            )
        )
    ).scalar_one()
    completion_tokens = (
        await session.execute(
            select(func.coalesce(func.sum(CallLog.completion_tokens), 0)).where(
                CallLog.created_at >= since_24h
            )
        )
    ).scalar_one()
    active_apps = (
        await session.execute(
            select(func.count(func.distinct(CallLog.app_id))).where(
                CallLog.created_at >= since_24h
            )
        )
    ).scalar_one()
    active_agents = (
        await session.execute(
            select(func.count(func.distinct(CallLog.agent_key))).where(
                CallLog.created_at >= since_24h
            )
        )
    ).scalar_one()

    # 区间内 & 上一周期总数（用于 delta）
    total_in_range = (
        await session.execute(
            select(func.count(CallLog.id)).where(
                CallLog.created_at >= range_from, CallLog.created_at <= range_to
            )
        )
    ).scalar_one()
    prev_period = (
        await session.execute(
            select(func.count(CallLog.id)).where(
                CallLog.created_at >= prev_from, CallLog.created_at < prev_to
            )
        )
    ).scalar_one()

    return Result.ok(
        OverviewItem(
            total_calls_24h=total_24h,
            total_calls_7d=total_7d,
            success_rate_24h=(success_24h / total_24h) if total_24h else 1.0,
            avg_duration_ms_24h=float(avg_dur or 0),
            total_prompt_tokens_24h=int(prompt_tokens or 0),
            total_completion_tokens_24h=int(completion_tokens or 0),
            active_apps_24h=active_apps,
            active_agents_24h=active_agents,
            range_from=range_from,
            range_to=range_to,
            total_calls_in_range=total_in_range,
            prev_period_calls=prev_period,
        )
    )


@router.get("/timeseries", response_model=Result[TimeSeriesResult])
async def timeseries(
    granularity: str = Query("auto", pattern="^(hour|day|auto)$"),
    hours: int = Query(24, ge=1, le=720),
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("dashboard:read")),
) -> Result[TimeSeriesResult]:
    """按 hour 或 day 分桶聚合 call_logs

    granularity='auto'：区间 ≤ 48h 用 hour，否则 day。
    """
    range_from, range_to = _resolve_range(from_ts, to_ts, hours)
    if granularity == "auto":
        span_hours = (range_to - range_from).total_seconds() / 3600
        granularity = "hour" if span_hours <= 48 else "day"
    bucket_fmt = granularity
    since = range_from

    # PG date_trunc 分桶
    bucket = func.date_trunc(bucket_fmt, CallLog.created_at).label("bucket")
    stmt = (
        select(
            bucket,
            func.count(CallLog.id).label("total"),
            func.count(CallLog.id)
            .filter(CallLog.success.is_(False))
            .label("errors"),
        )
        .where(CallLog.created_at >= since, CallLog.created_at <= range_to)
        .group_by(bucket)
        .order_by(bucket)
    )
    rows = (await session.execute(stmt)).all()
    return Result.ok(
        TimeSeriesResult(
            granularity=granularity,
            points=[
                TimePoint(ts=r.bucket, total=r.total, errors=r.errors) for r in rows
            ],
        )
    )


@router.get("/top-agents", response_model=Result[list[TopAgent]])
async def top_agents(
    limit: int = Query(10, ge=1, le=50),
    hours: int = Query(24, ge=1, le=720),
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("dashboard:read")),
) -> Result[list[TopAgent]]:
    range_from, range_to = _resolve_range(from_ts, to_ts, hours)
    rows = (
        await session.execute(
            select(CallLog.agent_key, func.count(CallLog.id).label("cnt"))
            .where(CallLog.created_at >= range_from, CallLog.created_at <= range_to)
            .group_by(CallLog.agent_key)
            .order_by(func.count(CallLog.id).desc())
            .limit(limit)
        )
    ).all()
    return Result.ok([TopAgent(agent_key=r.agent_key, count=r.cnt) for r in rows])


@router.get("/top-apps", response_model=Result[list[TopApp]])
async def top_apps(
    limit: int = Query(10, ge=1, le=50),
    hours: int = Query(24, ge=1, le=720),
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("dashboard:read")),
) -> Result[list[TopApp]]:
    range_from, range_to = _resolve_range(from_ts, to_ts, hours)
    rows = (
        await session.execute(
            select(CallLog.app_id, func.count(CallLog.id).label("cnt"))
            .where(CallLog.created_at >= range_from, CallLog.created_at <= range_to)
            .group_by(CallLog.app_id)
            .order_by(func.count(CallLog.id).desc())
            .limit(limit)
        )
    ).all()
    return Result.ok([TopApp(app_id=r.app_id, count=r.cnt) for r in rows])


# TODO: top-models —— call_logs 表暂无 model 字段，二期加 model 列后实现


# ── P22.1 Cost dashboard ────────────────────────────────


class CostTotalsResult(BaseModel):
    """卡片总额 + 上一周期 delta"""

    range_from: datetime
    range_to: datetime
    total_usd: float
    prev_total_usd: float | None = None
    delta_pct: float | None = None
    total_calls: int


class CostDimensionRow(BaseModel):
    label: str
    cost_usd: float  # 原始模型成本之和
    # C8：计费成本 = Σ(cost_usd × group_ratio)（含分组倍率）
    effective_cost_usd: float
    calls: int


class CostTimeseriesPoint(BaseModel):
    ts: datetime
    cost_usd: float


@router.get("/cost/totals", response_model=Result[CostTotalsResult])
async def cost_totals(
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    hours: int = Query(default=24, ge=1, le=24 * 90),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:read")),
) -> Result[CostTotalsResult]:
    """卡片总额 + 上一周期 delta"""
    rf, rt = _resolve_range(from_ts, to_ts, hours)
    span = rt - rf
    prev_to = rf
    prev_from = rf - span

    total_row = (
        await session.execute(
            select(
                func.coalesce(func.sum(CallLog.cost_usd), 0).label("total"),
                func.count(CallLog.id).label("cnt"),
            ).where(
                CallLog.created_at >= rf,
                CallLog.created_at <= rt,
                CallLog.parent_id.is_(None),
            )
        )
    ).one()
    prev_total = (
        await session.execute(
            select(func.coalesce(func.sum(CallLog.cost_usd), 0)).where(
                CallLog.created_at >= prev_from,
                CallLog.created_at <= prev_to,
                CallLog.parent_id.is_(None),
            )
        )
    ).scalar_one()

    total_usd = float(total_row.total or 0)
    prev_usd = float(prev_total or 0)
    delta_pct = None
    if prev_usd > 0:
        delta_pct = (total_usd - prev_usd) / prev_usd * 100.0

    return Result.ok(
        CostTotalsResult(
            range_from=rf,
            range_to=rt,
            total_usd=total_usd,
            prev_total_usd=prev_usd if prev_usd > 0 else None,
            delta_pct=delta_pct,
            total_calls=int(total_row.cnt or 0),
        )
    )


@router.get(
    "/cost/by-dimension", response_model=Result[list[CostDimensionRow]]
)
async def cost_by_dimension(
    dimension: str = Query(
        default="agent_key",
        pattern=(
            "^(agent_key|app_id|session_id|user_id|model_code|channel_id"
            "|workspace_id)$"
        ),
        description=(
            "按哪一维聚合：agent_key / app_id / session_id / user_id / "
            "model_code / channel_id / workspace_id"
        ),
    ),
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    hours: int = Query(default=24, ge=1, le=24 * 90),
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:read")),
) -> Result[list[CostDimensionRow]]:
    """按维度聚合 cost top-N（C8：含 user/model/channel/workspace 多维）

    cost_usd = Σ 原始模型成本；effective_cost_usd = Σ(cost_usd × group_ratio)，
    后者是实际计费额（分组倍率在 C5 写入时存死，这里直接乘）。
    """
    rf, rt = _resolve_range(from_ts, to_ts, hours)
    # workspace 维要 join apps 取 workspace_id；其余直接是 call_logs 列
    simple_cols = {
        "agent_key": CallLog.agent_key,
        "app_id": CallLog.app_id,
        "session_id": CallLog.session_id,
        "user_id": CallLog.user_id,
        "model_code": CallLog.model_code,
        "channel_id": CallLog.channel_id,
    }
    cost_sum = func.coalesce(func.sum(CallLog.cost_usd), 0).label("cost")
    effective_sum = func.coalesce(
        func.sum(CallLog.cost_usd * func.coalesce(CallLog.group_ratio, 1)), 0
    ).label("effective")
    cnt = func.count(CallLog.id).label("cnt")
    where_clause = (
        CallLog.created_at >= rf,
        CallLog.created_at <= rt,
        CallLog.parent_id.is_(None),
    )

    if dimension == "workspace_id":
        label_col = App.workspace_id
        stmt = (
            select(label_col.label("label"), cost_sum, effective_sum, cnt)
            .join(App, CallLog.app_id == App.app_key)
            .where(*where_clause)
            .group_by(label_col)
        )
    else:
        label_col = simple_cols[dimension]
        stmt = (
            select(label_col.label("label"), cost_sum, effective_sum, cnt)
            .where(*where_clause)
            .group_by(label_col)
        )

    rows = (
        await session.execute(
            stmt.order_by(func.sum(CallLog.cost_usd).desc().nullslast()).limit(
                limit
            )
        )
    ).all()
    return Result.ok(
        [
            CostDimensionRow(
                label=str(r.label) if r.label is not None else "<null>",
                cost_usd=float(r.cost or 0),
                effective_cost_usd=float(r.effective or 0),
                calls=int(r.cnt or 0),
            )
            for r in rows
        ]
    )


@router.get(
    "/cost/timeseries", response_model=Result[list[CostTimeseriesPoint]]
)
async def cost_timeseries(
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    hours: int = Query(default=24, ge=1, le=24 * 90),
    bucket: str = Query(default="hour", pattern="^(hour|day)$"),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:read")),
) -> Result[list[CostTimeseriesPoint]]:
    """按 hour / day 分桶的 cost 时间序列"""
    rf, rt = _resolve_range(from_ts, to_ts, hours)
    trunc = func.date_trunc(bucket, CallLog.created_at).label("ts")
    rows = (
        await session.execute(
            select(
                trunc,
                func.coalesce(func.sum(CallLog.cost_usd), 0).label("cost"),
            )
            .where(
                CallLog.created_at >= rf,
                CallLog.created_at <= rt,
                CallLog.parent_id.is_(None),
            )
            .group_by(trunc)
            .order_by(trunc.asc())
        )
    ).all()
    return Result.ok(
        [
            CostTimeseriesPoint(ts=r.ts, cost_usd=float(r.cost or 0))
            for r in rows
        ]
    )
