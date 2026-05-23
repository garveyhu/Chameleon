"""plugins HTTP 路由（/v1/admin/plugins）"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.core.infra.db import get_session
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.plugins import service
from chameleon.system.plugins.schemas import (
    InstallPluginRequest,
    PluginActionResult,
    PluginInstanceItem,
    UpdateConfigRequest,
)

router = APIRouter(prefix="/v1/admin/plugins", tags=["admin:plugins"])

_PERM_READ = "plugins:read"
_PERM_WRITE = "plugins:write"


@router.get("", response_model=Result[list[PluginInstanceItem]])
async def list_plugins(
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_READ)),
) -> Result[list[PluginInstanceItem]]:
    items = await service.list_plugins(session)
    return Result.ok(items)


@router.get("/{plugin_id}", response_model=Result[PluginInstanceItem])
async def get_plugin(
    plugin_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_READ)),
) -> Result[PluginInstanceItem]:
    item = await service.get_plugin(session, plugin_id)
    return Result.ok(item)


@router.post("/install", response_model=Result[PluginInstanceItem])
async def install_plugin(
    req: InstallPluginRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_WRITE)),
) -> Result[PluginInstanceItem]:
    item = await service.install_plugin(session, req)
    return Result.ok(item)


@router.post(
    "/{plugin_id}/enable", response_model=Result[PluginActionResult]
)
async def enable_plugin(
    plugin_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_WRITE)),
) -> Result[PluginActionResult]:
    r = await service.set_enabled(session, plugin_id, True)
    return Result.ok(r)


@router.post(
    "/{plugin_id}/disable", response_model=Result[PluginActionResult]
)
async def disable_plugin(
    plugin_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_WRITE)),
) -> Result[PluginActionResult]:
    r = await service.set_enabled(session, plugin_id, False)
    return Result.ok(r)


@router.post(
    "/{plugin_id}/reload", response_model=Result[PluginActionResult]
)
async def reload_plugin(
    plugin_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_WRITE)),
) -> Result[PluginActionResult]:
    r = await service.reload_plugin(session, plugin_id)
    return Result.ok(r)


@router.post(
    "/{plugin_id}/uninstall", response_model=Result[None]
)
async def uninstall_plugin(
    plugin_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_WRITE)),
) -> Result[None]:
    await service.uninstall_plugin(session, plugin_id)
    return Result.ok(None)


@router.post(
    "/{plugin_id}/config", response_model=Result[PluginInstanceItem]
)
async def update_plugin_config(
    plugin_id: int,
    req: UpdateConfigRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_WRITE)),
) -> Result[PluginInstanceItem]:
    item = await service.update_config(session, plugin_id, req)
    return Result.ok(item)
