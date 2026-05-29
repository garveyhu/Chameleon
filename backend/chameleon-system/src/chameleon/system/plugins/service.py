"""plugins admin service —— 包装 PluginRegistry，给 API 层用

启停 / reload 后会同步 PROVIDERS / TOOLS registry —— 因为 P19.2 PR #33 已让
build_provider_registry 接受 disabled_keys 过滤，这里只需调 `reload_agent_registry`
重建 PROVIDERS 即可（不重启进程）。
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.plugins import PluginManifest
from chameleon.data.models import PluginInstance
from chameleon.integrations.plugins import plugin_registry
from chameleon.system.plugins.schemas import (
    InstallPluginRequest,
    PluginActionResult,
    PluginInstanceItem,
    UpdateConfigRequest,
)

# ── 查询 ────────────────────────────────────────────


async def list_plugins(session: AsyncSession) -> list[PluginInstanceItem]:
    rows = (
        (
            await session.execute(
                select(PluginInstance).order_by(
                    PluginInstance.source != "builtin",  # builtin 优先
                    PluginInstance.installed_at.asc(),
                )
            )
        )
        .scalars()
        .all()
    )
    return [PluginInstanceItem.model_validate(r) for r in rows]


async def get_plugin(
    session: AsyncSession, plugin_id: int
) -> PluginInstanceItem:
    row = await _load(session, plugin_id)
    return PluginInstanceItem.model_validate(row)


# ── 安装 ────────────────────────────────────────────


async def install_plugin(
    session: AsyncSession, req: InstallPluginRequest
) -> PluginInstanceItem:
    try:
        manifest = PluginManifest.model_validate(req.manifest)
    except Exception as e:
        raise BusinessError(
            ResultCode.ValidationError, message=f"manifest 校验失败: {e}"
        )

    try:
        entry = await plugin_registry.install(
            session,
            manifest=manifest,
            source=req.source,
            source_url=req.source_url,
            config=req.config,
        )
    except ValueError as e:
        # sandbox / 重复 plugin_key
        raise BusinessError(ResultCode.Fail, message=str(e))
    except (ImportError, AttributeError) as e:
        raise BusinessError(
            ResultCode.Fail,
            message=f"entrypoint 加载失败: {e}（确认插件包已 pip 安装到 venv）",
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("plugin install unexpected | manifest={}", req.manifest)
        raise BusinessError(ResultCode.Fail, message=f"安装失败: {e}")

    await _refresh_provider_registry()
    row = (
        await session.execute(
            select(PluginInstance).where(
                PluginInstance.plugin_key == entry.plugin_key
            )
        )
    ).scalar_one()
    return PluginInstanceItem.model_validate(row)


# ── enable / disable / reload / uninstall ───────────


async def set_enabled(
    session: AsyncSession, plugin_id: int, enabled: bool
) -> PluginActionResult:
    row = await _load(session, plugin_id)
    ok = await plugin_registry.set_enabled(session, row.plugin_key, enabled)
    await _refresh_provider_registry()
    return PluginActionResult(
        plugin_key=row.plugin_key,
        enabled=enabled,
        loaded=ok and enabled,
        message=None if ok else "resolve 失败；DB 已切但 registry 未挂",
    )


async def reload_plugin(
    session: AsyncSession, plugin_id: int
) -> PluginActionResult:
    row = await _load(session, plugin_id)
    entry = await plugin_registry.reload(session, row.plugin_key)
    await _refresh_provider_registry()
    return PluginActionResult(
        plugin_key=row.plugin_key,
        enabled=row.enabled,
        loaded=entry is not None,
        message=None if entry else "reload 未生效（plugin 已 disabled 或 entrypoint 异常）",
    )


async def uninstall_plugin(
    session: AsyncSession, plugin_id: int
) -> None:
    row = await _load(session, plugin_id)
    try:
        ok = await plugin_registry.uninstall(session, row.plugin_key)
    except ValueError as e:
        raise BusinessError(ResultCode.Fail, message=str(e))
    if not ok:
        raise BusinessError(
            ResultCode.NotFound, message=f"plugin 不存在: {row.plugin_key}"
        )
    await _refresh_provider_registry()


# ── update config ───────────────────────────────────


async def update_config(
    session: AsyncSession, plugin_id: int, req: UpdateConfigRequest
) -> PluginInstanceItem:
    row = await _load(session, plugin_id)
    await session.execute(
        update(PluginInstance)
        .where(PluginInstance.id == row.id)
        .values(config=req.config)
    )
    await session.commit()
    fresh = await _load(session, plugin_id)
    return PluginInstanceItem.model_validate(fresh)


# ── helpers ─────────────────────────────────────────


async def _load(session: AsyncSession, plugin_id: int) -> PluginInstance:
    row = (
        await session.execute(
            select(PluginInstance).where(PluginInstance.id == plugin_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.NotFound, message=f"plugin 不存在: {plugin_id}"
        )
    return row


async def _refresh_provider_registry() -> None:
    """plugin 启停后让 PROVIDERS 重新算 disabled 集

    实现：调 base.registry.init_registry —— 已加幂等 guard，重复调用会 skip；
    这里强制重置 _BUILT 让它重跑。
    """
    try:
        from chameleon.providers.base import registry as base_reg

        base_reg.reset_registry_for_test()
        await base_reg.init_registry()
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "provider registry refresh failed (启停可能未在运行时生效): {}", e
        )
