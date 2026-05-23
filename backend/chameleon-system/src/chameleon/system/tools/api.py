"""tools HTTP 路由（/v1/admin/tools）"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.core.infra.db import get_session
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.tools import service as tool_service
from chameleon.system.tools.schemas import (
    CreateToolInstanceRequest,
    ToolCatalogItem,
    ToolInstanceItem,
    UpdateToolInstanceRequest,
)

router = APIRouter(prefix="/v1/admin/tools", tags=["admin:tools"])


@router.get("/catalog", response_model=Result[list[ToolCatalogItem]])
async def list_catalog(
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("tools:read")),
) -> Result[list[ToolCatalogItem]]:
    """列出全部内置 Tool + 当前 admin 配的实例状态"""
    items = await tool_service.list_catalog(session)
    return Result.ok(items)


@router.get("", response_model=Result[list[ToolInstanceItem]])
async def list_instances(
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("tools:read")),
) -> Result[list[ToolInstanceItem]]:
    items = await tool_service.list_instances(session)
    return Result.ok(items)


@router.get("/{instance_id}", response_model=Result[ToolInstanceItem])
async def get_instance(
    instance_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("tools:read")),
) -> Result[ToolInstanceItem]:
    item = await tool_service.get_instance(session, instance_id)
    return Result.ok(item)


@router.post("", response_model=Result[ToolInstanceItem])
async def create_instance(
    req: CreateToolInstanceRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("tools:write")),
) -> Result[ToolInstanceItem]:
    item = await tool_service.create_instance(session, req)
    return Result.ok(item)


@router.post("/{instance_id}/update", response_model=Result[ToolInstanceItem])
async def update_instance(
    instance_id: int,
    req: UpdateToolInstanceRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("tools:write")),
) -> Result[ToolInstanceItem]:
    item = await tool_service.update_instance(session, instance_id, req)
    return Result.ok(item)


@router.post("/{instance_id}/delete", response_model=Result[None])
async def delete_instance(
    instance_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("tools:delete")),
) -> Result[None]:
    await tool_service.delete_instance(session, instance_id)
    return Result.ok(None)
