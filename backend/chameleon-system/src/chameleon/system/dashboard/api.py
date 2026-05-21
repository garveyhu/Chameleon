"""dashboard HTTP 路由 (/v1/admin/dashboard)

- overview：综合卡片数据
- timeseries：时序聚合（按 hour / day 分桶）
- top-agents / top-apps：top N 列表
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.core.infra.db import get_session
from chameleon.core.models import CallLog
from chameleon.system.auth.dependencies import require_permission


# ── DTO ────────────────────────────────────────────────────


class OverviewItem(BaseModel):
    total_calls_24h: int
    total_calls_7d: int
    success_rate_24h: float
    avg_duration_ms_24h: float
    total_prompt_tokens_24h: int
    total_completion_tokens_24h: int
    active_apps_24h: int
    active_agents_24h: int


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
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("dashboard:read")),
) -> Result[OverviewItem]:
    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)

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
        )
    )


@router.get("/timeseries", response_model=Result[TimeSeriesResult])
async def timeseries(
    granularity: str = Query("hour", pattern="^(hour|day)$"),
    hours: int = Query(24, ge=1, le=720),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("dashboard:read")),
) -> Result[TimeSeriesResult]:
    """按 hour 或 day 分桶聚合 call_logs"""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    bucket_fmt = "hour" if granularity == "hour" else "day"

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
        .where(CallLog.created_at >= since)
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
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("dashboard:read")),
) -> Result[list[TopAgent]]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (
        await session.execute(
            select(CallLog.agent_key, func.count(CallLog.id).label("cnt"))
            .where(CallLog.created_at >= since)
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
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("dashboard:read")),
) -> Result[list[TopApp]]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (
        await session.execute(
            select(CallLog.app_id, func.count(CallLog.id).label("cnt"))
            .where(CallLog.created_at >= since)
            .group_by(CallLog.app_id)
            .order_by(func.count(CallLog.id).desc())
            .limit(limit)
        )
    ).all()
    return Result.ok([TopApp(app_id=r.app_id, count=r.cnt) for r in rows])
