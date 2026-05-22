"""api_key 模块 HTTP 路由

挂点：/v1/admin/api-keys/*
鉴权：JWT + api_keys:read / api_keys:write
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import PageParams, PageResult, Result
from chameleon.core.infra.db import get_session
from chameleon.system.api_key import service
from chameleon.system.api_key.schemas import (
    ApiKeyCreated,
    ApiKeyItem,
    CreateApiKeyRequest,
)
from chameleon.system.auth.dependencies import require_permission

router = APIRouter(prefix="/v1/admin/api-keys", tags=["admin:api-keys"])


@router.post("", response_model=Result[ApiKeyCreated])
async def create_api_key(
    req: CreateApiKeyRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("api_keys:write")),
) -> Result[ApiKeyCreated]:
    created = await service.create_api_key(session, req, created_by_user_id=None)
    return Result.ok(created)


@router.get("", response_model=Result[PageResult[ApiKeyItem]])
async def list_api_keys(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    include_revoked: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("api_keys:read")),
) -> Result[PageResult[ApiKeyItem]]:
    result = await service.list_api_keys(
        session,
        PageParams(page=page, page_size=page_size),
        include_revoked=include_revoked,
    )
    return Result.ok(result)


@router.post("/{key_id}/revoke", response_model=Result[ApiKeyItem])
async def revoke_api_key(
    key_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("api_keys:delete")),
) -> Result[ApiKeyItem]:
    item = await service.revoke_api_key(session, key_id)
    return Result.ok(item)
