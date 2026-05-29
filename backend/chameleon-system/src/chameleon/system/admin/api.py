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
    SessionItem,
    TraceTreeNode,
)
from chameleon.system.auth.dependencies import require_permission

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/call-logs", response_model=Result[PageResult[CallLogItem]])
async def list_call_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    app_id: str | None = Query(None),
    agent_key: str | None = Query(None),
    channel: str | None = Query(None, description="渠道：api/openai/embed/internal/…"),
    model_code: str | None = Query(None),
    session_id: str | None = Query(None),
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
        channel=channel,
        model_code=model_code,
        session_id=session_id,
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


@router.get(
    "/call-logs/{request_id}/tree", response_model=Result[TraceTreeNode]
)
async def get_call_log_tree(
    request_id: str,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:read")),
) -> Result[TraceTreeNode]:
    """以 request_id 为根，返完整嵌套 observation 树（含所有后代节点）"""
    tree = await service.get_trace_tree(session, request_id)
    return Result.ok(tree)


@router.get("/sessions", response_model=Result[PageResult[SessionItem]])
async def list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    agent_key: str | None = Query(None),
    end_user_id: str | None = Query(None),
    since: datetime | None = Query(None, description="ISO8601 起始（含）"),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:read")),
) -> Result[PageResult[SessionItem]]:
    """会话（thread）列表：按 ChatSession 维度，区别于 /call-logs 的 trace（单次运行）"""
    result = await service.list_sessions(
        session,
        PageParams(page=page, page_size=page_size),
        agent_key=agent_key,
        end_user_id=end_user_id,
        since=since,
    )
    return Result.ok(result)


@router.get("/providers/status", response_model=Result[list[ProviderStatusItem]])
async def providers_status(
    _: object = Depends(require_permission("providers:read")),
) -> Result[list[ProviderStatusItem]]:
    items = await service.providers_status()
    return Result.ok(items)
