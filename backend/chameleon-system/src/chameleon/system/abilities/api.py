"""abilities HTTP 路由 (/v1/admin/abilities)"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.core.infra.db import get_session
from chameleon.system.abilities import service as ability_service
from chameleon.system.abilities.schemas import (
    AbilityItem,
    CreateAbilityRequest,
    UpdateAbilityRequest,
)
from chameleon.system.auth.dependencies import require_permission

router = APIRouter(prefix="/v1/admin/abilities", tags=["admin:abilities"])


@router.get("", response_model=Result[list[AbilityItem]])
async def list_abilities(
    model_code: str | None = Query(default=None),
    group_id: int | None = Query(
        default=None,
        description="0 = 仅全局 ability；>0 = 精确匹配；不传 = 不过滤",
    ),
    channel_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("abilities:read")),
) -> Result[list[AbilityItem]]:
    items = await ability_service.list_abilities(
        session,
        model_code=model_code,
        group_id=group_id,
        channel_id=channel_id,
    )
    return Result.ok(items)


@router.post("", response_model=Result[AbilityItem])
async def create_ability(
    req: CreateAbilityRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("abilities:write")),
) -> Result[AbilityItem]:
    item = await ability_service.create_ability(session, req)
    return Result.ok(item)


@router.post("/{ability_id}/update", response_model=Result[AbilityItem])
async def update_ability(
    ability_id: int,
    req: UpdateAbilityRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("abilities:write")),
) -> Result[AbilityItem]:
    item = await ability_service.update_ability(session, ability_id, req)
    return Result.ok(item)


@router.post("/{ability_id}/delete", response_model=Result[None])
async def delete_ability(
    ability_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("abilities:delete")),
) -> Result[None]:
    await ability_service.delete_ability(session, ability_id)
    return Result.ok(None)
