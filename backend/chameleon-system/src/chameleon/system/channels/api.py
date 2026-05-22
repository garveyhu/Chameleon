"""channels HTTP 路由 (/v1/admin/channels)

挂点：/v1/admin/channels/*
路由层零业务 —— 全部委托给 service。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.core.infra.db import get_session
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.channels import service as channel_service
from chameleon.system.channels.schemas import (
    ChannelItem,
    CreateChannelRequest,
    UpdateChannelRequest,
)

router = APIRouter(prefix="/v1/admin/channels", tags=["admin:channels"])


@router.get("", response_model=Result[list[ChannelItem]])
async def list_channels(
    provider_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("channels:read")),
) -> Result[list[ChannelItem]]:
    items = await channel_service.list_channels(
        session, provider_id=provider_id, status=status
    )
    return Result.ok(items)


@router.get("/{channel_id}", response_model=Result[ChannelItem])
async def get_channel(
    channel_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("channels:read")),
) -> Result[ChannelItem]:
    item = await channel_service.get_channel(session, channel_id)
    return Result.ok(item)


@router.post("", response_model=Result[ChannelItem])
async def create_channel(
    req: CreateChannelRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("channels:write")),
) -> Result[ChannelItem]:
    item = await channel_service.create_channel(session, req)
    return Result.ok(item)


@router.post("/{channel_id}/update", response_model=Result[ChannelItem])
async def update_channel(
    channel_id: int,
    req: UpdateChannelRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("channels:write")),
) -> Result[ChannelItem]:
    item = await channel_service.update_channel(session, channel_id, req)
    return Result.ok(item)


@router.post("/{channel_id}/delete", response_model=Result[None])
async def delete_channel(
    channel_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("channels:delete")),
) -> Result[None]:
    await channel_service.delete_channel(session, channel_id)
    return Result.ok(None)
