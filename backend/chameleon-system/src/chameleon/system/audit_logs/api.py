"""audit_logs HTTP 路由（仅查询）"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import PageResult, Result
from chameleon.core.infra.db import get_session
from chameleon.core.models import AuditLog
from chameleon.system.auth.dependencies import require_permission


class AuditLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: int | None = None
    actor_username: str | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    before: dict | None = None
    after: dict | None = None
    ip: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
    created_at: datetime


router = APIRouter(prefix="/v1/admin/audit-logs", tags=["admin:audit-logs"])


@router.get("", response_model=Result[PageResult[AuditLogItem]])
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    actor_user_id: int | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    action: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("audit_logs:read")),
) -> Result[PageResult[AuditLogItem]]:
    base = select(AuditLog)
    if actor_user_id is not None:
        base = base.where(AuditLog.actor_user_id == actor_user_id)
    if resource_type:
        base = base.where(AuditLog.resource_type == resource_type)
    if action:
        base = base.where(AuditLog.action == action)

    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                base.order_by(AuditLog.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return Result.ok(
        PageResult(
            items=[AuditLogItem.model_validate(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )
    )
