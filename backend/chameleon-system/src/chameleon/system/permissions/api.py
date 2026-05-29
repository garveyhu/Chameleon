"""permissions 只读路由

permission 由 seed 决定，前端列出来给 role 分配用。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.data.infra.db import get_session
from chameleon.data.models import Permission
from chameleon.system.auth.dependencies import require_permission


class PermissionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    resource: str
    action: str
    description: str | None = None


router = APIRouter(prefix="/v1/admin/permissions", tags=["admin:permissions"])


@router.get("", response_model=Result[list[PermissionItem]])
async def list_permissions(
    resource: str | None = Query(default=None, description="按 resource 过滤"),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("roles:read")),
) -> Result[list[PermissionItem]]:
    stmt = select(Permission).order_by(Permission.resource, Permission.action)
    if resource:
        stmt = stmt.where(Permission.resource == resource)
    rows = (await session.execute(stmt)).scalars().all()
    return Result.ok([PermissionItem.model_validate(r) for r in rows])
