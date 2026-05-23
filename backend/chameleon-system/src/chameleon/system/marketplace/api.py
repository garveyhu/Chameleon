"""marketplace HTTP 路由（/v1/admin/marketplace）"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.core.infra.db import get_session
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.marketplace import service
from chameleon.system.marketplace.schemas import (
    AddRegistryRequest,
    InstallFromRemoteRequest,
    MarketplaceEntry,
    RegistryItem,
    SyncResult,
    UpdateRegistryRequest,
)

router = APIRouter(prefix="/v1/admin/marketplace", tags=["admin:marketplace"])

# 复用 plugins 权限：marketplace 是 plugin 域的子集
_PERM_READ = "plugins:read"
_PERM_WRITE = "plugins:write"


# ── registries CRUD ───────────────────────────────────


@router.get(
    "/registries", response_model=Result[list[RegistryItem]]
)
async def list_registries(
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_READ)),
) -> Result[list[RegistryItem]]:
    return Result.ok(await service.list_registries(session))


@router.post("/registries", response_model=Result[RegistryItem])
async def add_registry(
    req: AddRegistryRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_WRITE)),
) -> Result[RegistryItem]:
    return Result.ok(await service.add_registry(session, req))


@router.post(
    "/registries/{registry_id}/update", response_model=Result[RegistryItem]
)
async def update_registry(
    registry_id: int,
    req: UpdateRegistryRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_WRITE)),
) -> Result[RegistryItem]:
    return Result.ok(
        await service.update_registry(session, registry_id, req)
    )


@router.post(
    "/registries/{registry_id}/delete", response_model=Result[None]
)
async def delete_registry(
    registry_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_WRITE)),
) -> Result[None]:
    await service.delete_registry(session, registry_id)
    return Result.ok(None)


@router.post(
    "/registries/{registry_id}/sync", response_model=Result[SyncResult]
)
async def sync_registry(
    registry_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_WRITE)),
) -> Result[SyncResult]:
    return Result.ok(await service.sync_registry(session, registry_id))


# ── search / install ──────────────────────────────────


@router.get("/search", response_model=Result[list[MarketplaceEntry]])
async def search(
    q: str = Query(default="", max_length=128),
    tag: str | None = Query(default=None, max_length=64),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_READ)),
) -> Result[list[MarketplaceEntry]]:
    return Result.ok(await service.search(session, query=q, tag=tag))


@router.post("/install", response_model=Result[dict])
async def install(
    req: InstallFromRemoteRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_WRITE)),
) -> Result[dict]:
    return Result.ok(await service.install_from_remote(session, req))
