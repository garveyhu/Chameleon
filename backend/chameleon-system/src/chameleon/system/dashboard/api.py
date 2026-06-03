"""dashboard HTTP 路由 (/v1/admin/dashboard)

薄 handler：参数校验 → 调 service → Result 包装。聚合逻辑全部在 service.py。

时间区间：from_ts/to_ts（ISO datetime）优先，否则回退 hours（向下兼容）。
所有指标区间口径 + 只算 trace 根行（parent_id IS NULL），详见 service.py。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.data.infra.db import get_session
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.dashboard import schemas, service

router = APIRouter(prefix="/v1/admin/dashboard", tags=["admin:dashboard"])

_DIMENSION_PATTERN = (
    "^(agent_key|app_id|session_id|user_id|end_user_id|model_code|channel|error_class)$"
)


@router.get("/overview", response_model=Result[schemas.OverviewItem])
async def overview(
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    hours: int = Query(default=24, ge=1, le=24 * 90),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("dashboard:read")),
) -> Result[schemas.OverviewItem]:
    rf, rt = service.resolve_range(from_ts, to_ts, hours)
    return Result.ok(await service.get_overview(session, rf, rt))


@router.get("/timeseries", response_model=Result[schemas.TimeSeriesResult])
async def timeseries(
    granularity: str = Query("auto", pattern="^(hour|day|auto)$"),
    hours: int = Query(24, ge=1, le=24 * 90),
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("dashboard:read")),
) -> Result[schemas.TimeSeriesResult]:
    rf, rt = service.resolve_range(from_ts, to_ts, hours)
    return Result.ok(await service.get_timeseries(session, rf, rt, granularity))


@router.get("/top-dimension", response_model=Result[list[schemas.TopDimensionRow]])
async def top_dimension(
    dimension: str = Query(default="agent_key", pattern=_DIMENSION_PATTERN),
    limit: int = Query(10, ge=1, le=50),
    hours: int = Query(24, ge=1, le=24 * 90),
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("dashboard:read")),
) -> Result[list[schemas.TopDimensionRow]]:
    rf, rt = service.resolve_range(from_ts, to_ts, hours)
    return Result.ok(await service.get_top_dimension(session, rf, rt, dimension, limit))


@router.get("/distribution", response_model=Result[list[schemas.DistributionRow]])
async def distribution(
    dimension: str = Query(default="channel", pattern=_DIMENSION_PATTERN),
    limit: int = Query(10, ge=1, le=50),
    hours: int = Query(24, ge=1, le=24 * 90),
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("dashboard:read")),
) -> Result[list[schemas.DistributionRow]]:
    rf, rt = service.resolve_range(from_ts, to_ts, hours)
    return Result.ok(await service.get_distribution(session, rf, rt, dimension, limit))


@router.get("/cost/totals", response_model=Result[schemas.CostTotalsResult])
async def cost_totals(
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    hours: int = Query(default=24, ge=1, le=24 * 90),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:read")),
) -> Result[schemas.CostTotalsResult]:
    rf, rt = service.resolve_range(from_ts, to_ts, hours)
    return Result.ok(await service.get_cost_totals(session, rf, rt))


@router.get("/cost/by-dimension", response_model=Result[list[schemas.CostDimensionRow]])
async def cost_by_dimension(
    dimension: str = Query(default="agent_key", pattern=_DIMENSION_PATTERN),
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    hours: int = Query(default=24, ge=1, le=24 * 90),
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:read")),
) -> Result[list[schemas.CostDimensionRow]]:
    rf, rt = service.resolve_range(from_ts, to_ts, hours)
    return Result.ok(
        await service.get_cost_by_dimension(session, rf, rt, dimension, limit)
    )


@router.get(
    "/cost/timeseries", response_model=Result[list[schemas.CostTimeseriesPoint]]
)
async def cost_timeseries(
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    hours: int = Query(default=24, ge=1, le=24 * 90),
    bucket: str = Query(default="hour", pattern="^(hour|day)$"),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:read")),
) -> Result[list[schemas.CostTimeseriesPoint]]:
    rf, rt = service.resolve_range(from_ts, to_ts, hours)
    return Result.ok(await service.get_cost_timeseries(session, rf, rt, bucket))
