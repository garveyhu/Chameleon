"""admin 模块 HTTP 路由

挂点：
  GET /v1/admin/call-logs               —— 四维过滤
  GET /v1/admin/call-logs/{id}          —— 详情含 spans + payload
  GET /v1/admin/providers/status        —— 实时探活
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import PageParams, PageResult, Result
from chameleon.core.infra.db import get_session
from chameleon.system.admin import service
from chameleon.system.admin.schemas import (
    CallLogDetailItem,
    CallLogItem,
    ProviderStatusItem,
)
from chameleon.system.auth.dependencies import require_permission

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/call-logs", response_model=Result[PageResult[CallLogItem]])
async def list_call_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    app_id: str | None = Query(None),
    agent_key: str | None = Query(None),
    since: datetime | None = Query(None, description="ISO8601 起始（含）"),
    until: datetime | None = Query(None, description="ISO8601 结束（含）"),
    success: bool | None = Query(None),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:read")),
) -> Result[PageResult[CallLogItem]]:
    result = await service.list_call_logs(
        session,
        PageParams(page=page, page_size=page_size),
        app_id=app_id,
        agent_key=agent_key,
        since=since,
        until=until,
        success=success,
    )
    return Result.ok(result)


@router.get(
    "/call-logs/{call_log_id}", response_model=Result[CallLogDetailItem]
)
async def get_call_log(
    call_log_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:read")),
) -> Result[CallLogDetailItem]:
    item = await service.get_call_log(session, call_log_id)
    return Result.ok(item)


@router.get("/providers/status", response_model=Result[list[ProviderStatusItem]])
async def providers_status(
    _: object = Depends(require_permission("providers:read")),
) -> Result[list[ProviderStatusItem]]:
    items = await service.providers_status()
    return Result.ok(items)
