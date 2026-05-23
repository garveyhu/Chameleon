"""PluginRegistry —— P19.2 PR #33

职责：
- bootstrap(): 首次启动 seed builtin（local/dify/fastgpt）到 plugin_instances；
  幂等（已存在则跳过）
- load_all(session): 拉所有 enabled=True 行 → 返回 PluginEntry 列表（供调用方决定如何接入 PROVIDERS）
- set_enabled(session, plugin_key, enabled): 切换启停 + 同步内部 cache（不重启进程）
- reload(plugin_key): importlib.reload 模块 + 重新解析 entrypoint（class 重新绑定）
- disabled_keys_for_type(session, type): 查 type 维度禁用集，给 build_provider_registry 反向过滤

红线（plan §2 新增）：
- ⛔ 加载必须 async + 5s 超时上限（reload 同步导入慢的库不能拖垮事件循环）
- ⛔ manifest 校验失败的 plugin **永不加载**，不能"半生不熟"
- ⛔ 卸载用 weakref 池追踪实例，避免 importlib.reload 后老类残留
"""

from __future__ import annotations

import asyncio
import importlib
import sys
import weakref
from typing import Any

from loguru import logger
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.models import PluginInstance
from chameleon.core.plugins.manifest import PluginManifest

_LOAD_TIMEOUT_SEC = 5.0

# Plugin 不许把 entrypoint 指向这些内部模块路径，防越权拿 DB / admin / API 内部能力
_FORBIDDEN_ENTRYPOINT_PREFIXES = (
    "chameleon.core.models",
    "chameleon.core.infra",
    "chameleon.core.utils.crypto",
    "chameleon.system",
    "chameleon.api",
    "chameleon.app",
)


def assert_entrypoint_not_internal(entrypoint: str) -> None:
    """SDK 沙箱：拒绝将内部模块直接当 plugin entrypoint 暴露"""
    module_path, _, _ = entrypoint.partition(":")
    for prefix in _FORBIDDEN_ENTRYPOINT_PREFIXES:
        if module_path == prefix or module_path.startswith(prefix + "."):
            raise ValueError(
                f"entrypoint 命中内部模块沙箱: {module_path!r}; "
                f"plugin 不能直接挂载 {prefix}.*"
            )


class PluginEntry:
    """已 resolve 的 plugin 运行时实体"""

    def __init__(
        self,
        manifest: PluginManifest,
        symbol: Any,
        instance_id: int,
        source: str,
    ) -> None:
        self.manifest = manifest
        self.symbol = symbol  # entrypoint 解析出来的类 / 实例
        self.instance_id = instance_id
        self.source = source

    @property
    def plugin_key(self) -> str:
        return self.manifest.name

    @property
    def plugin_type(self) -> str:
        return self.manifest.type


class PluginRegistry:
    """全局 plugin 注册表 —— 单例，lifespan 拿"""

    def __init__(self) -> None:
        self._entries: dict[str, PluginEntry] = {}
        # weakref 池：插件实例 GC 追踪，便于 reload 后释放
        self._instances: weakref.WeakValueDictionary[str, Any] = (
            weakref.WeakValueDictionary()
        )

    # ── 查询 ────────────────────────────────────────

    def get(self, plugin_key: str) -> PluginEntry | None:
        return self._entries.get(plugin_key)

    def list_by_type(self, plugin_type: str) -> list[PluginEntry]:
        return [
            e for e in self._entries.values() if e.plugin_type == plugin_type
        ]

    def all_keys(self) -> list[str]:
        return sorted(self._entries.keys())

    async def disabled_keys_for_type(
        self, session: AsyncSession, plugin_type: str
    ) -> set[str]:
        """type 维度禁用集 —— 给 provider registry 反向过滤"""
        rows = (
            (
                await session.execute(
                    select(PluginInstance.plugin_key).where(
                        PluginInstance.type == plugin_type,
                        PluginInstance.enabled.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
        return set(rows)

    # ── 加载 ────────────────────────────────────────

    async def load_all(self, session: AsyncSession) -> list[PluginEntry]:
        """从 DB 拉所有 enabled=True 行并 resolve；返回加载成功的 entries"""
        rows = (
            (
                await session.execute(
                    select(PluginInstance).where(
                        PluginInstance.enabled.is_(True)
                    )
                )
            )
            .scalars()
            .all()
        )
        self._entries.clear()
        loaded: list[PluginEntry] = []
        for row in rows:
            try:
                entry = await asyncio.wait_for(
                    self._resolve(row), timeout=_LOAD_TIMEOUT_SEC
                )
                self._entries[entry.plugin_key] = entry
                loaded.append(entry)
            except asyncio.TimeoutError:
                logger.warning(
                    "plugin load timeout | key={} | >={}s",
                    row.plugin_key,
                    _LOAD_TIMEOUT_SEC,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "plugin load failed | key={} | err={}",
                    row.plugin_key,
                    e,
                )
        return loaded

    async def _resolve(self, row: PluginInstance) -> PluginEntry:
        """校验 manifest + import entrypoint 模块 + 取 symbol"""
        manifest = PluginManifest.model_validate(row.manifest)
        module_path, symbol_name = manifest.parse_entrypoint()
        module = importlib.import_module(module_path)
        symbol = getattr(module, symbol_name, None)
        if symbol is None:
            raise ImportError(
                f"entrypoint symbol not found: {module_path}.{symbol_name}"
            )
        return PluginEntry(
            manifest=manifest,
            symbol=symbol,
            instance_id=row.id,
            source=row.source,
        )

    # ── 切换 ────────────────────────────────────────

    async def set_enabled(
        self, session: AsyncSession, plugin_key: str, enabled: bool
    ) -> bool:
        """admin enable/disable —— 同步 DB + 内部 cache（不重启进程）"""
        await session.execute(
            update(PluginInstance)
            .where(PluginInstance.plugin_key == plugin_key)
            .values(enabled=enabled)
        )
        await session.commit()
        # 同步 cache
        if not enabled:
            self._entries.pop(plugin_key, None)
        else:
            row = (
                await session.execute(
                    select(PluginInstance).where(
                        PluginInstance.plugin_key == plugin_key
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                try:
                    entry = await asyncio.wait_for(
                        self._resolve(row), timeout=_LOAD_TIMEOUT_SEC
                    )
                    self._entries[entry.plugin_key] = entry
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "plugin re-enable load failed | key={} | err={}",
                        plugin_key,
                        e,
                    )
                    return False
        logger.info("plugin {} | key={}", "enabled" if enabled else "disabled", plugin_key)
        return True

    async def reload(
        self, session: AsyncSession, plugin_key: str
    ) -> PluginEntry | None:
        """importlib.reload 入口模块 + 重新 resolve symbol"""
        row = (
            await session.execute(
                select(PluginInstance).where(
                    PluginInstance.plugin_key == plugin_key
                )
            )
        ).scalar_one_or_none()
        if row is None or not row.enabled:
            self._entries.pop(plugin_key, None)
            return None

        manifest = PluginManifest.model_validate(row.manifest)
        module_path, _ = manifest.parse_entrypoint()
        if module_path in sys.modules:
            try:
                importlib.reload(sys.modules[module_path])
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "plugin reload importlib.reload failed | key={} | err={}",
                    plugin_key,
                    e,
                )
        try:
            entry = await asyncio.wait_for(
                self._resolve(row), timeout=_LOAD_TIMEOUT_SEC
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("plugin reload resolve failed | key={} | err={}", plugin_key, e)
            return None
        self._entries[plugin_key] = entry
        logger.info("plugin reloaded | key={}", plugin_key)
        return entry

    # ── 安装 / 卸载 ─────────────────────────────────

    async def install(
        self,
        session: AsyncSession,
        *,
        manifest: PluginManifest,
        source: str = "local",
        source_url: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> PluginEntry:
        """落 DB + 立刻加载；幂等：plugin_key 已存在则报错（让调用方决定 reinstall）

        sandbox：entrypoint 命中内部模块前缀直接拒绝
        """
        assert_entrypoint_not_internal(manifest.entrypoint)

        existing = (
            await session.execute(
                select(PluginInstance).where(
                    PluginInstance.plugin_key == manifest.name
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ValueError(
                f"plugin_key 已存在: {manifest.name}; 先 uninstall 再 install 新版本"
            )

        row = PluginInstance(
            plugin_key=manifest.name,
            name=manifest.name,
            type=manifest.type,
            version=manifest.version,
            source=source,
            source_url=source_url,
            manifest=manifest.model_dump(),
            config=config or {},
            enabled=True,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)

        entry = await asyncio.wait_for(
            self._resolve(row), timeout=_LOAD_TIMEOUT_SEC
        )
        self._entries[entry.plugin_key] = entry
        logger.info("plugin installed | key={} | source={}", manifest.name, source)
        return entry

    async def uninstall(
        self, session: AsyncSession, plugin_key: str
    ) -> bool:
        """从 DB 删除 + 从 cache 弹出；builtin 拒绝卸载"""
        row = (
            await session.execute(
                select(PluginInstance).where(
                    PluginInstance.plugin_key == plugin_key
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        if row.source == "builtin":
            raise ValueError(
                f"builtin plugin 禁止卸载: {plugin_key}；可 disable 关闭"
            )
        await session.delete(row)
        await session.commit()
        self._entries.pop(plugin_key, None)
        logger.info("plugin uninstalled | key={}", plugin_key)
        return True

    # ── builtin seed ────────────────────────────────

    async def bootstrap_builtin(
        self,
        session: AsyncSession,
        builtins: list[dict[str, Any]],
    ) -> int:
        """首次启动 seed builtin —— 幂等。

        builtins: [{manifest: dict, ...}]，每条由调用方提供已校验的 PluginManifest 字典
        """
        existing_keys = {
            r[0]
            for r in (
                await session.execute(select(PluginInstance.plugin_key))
            ).all()
        }
        added = 0
        for spec in builtins:
            try:
                manifest = PluginManifest.model_validate(spec["manifest"])
            except ValidationError as e:
                logger.warning(
                    "skip builtin: invalid manifest | err={}", e
                )
                continue
            if manifest.name in existing_keys:
                continue
            row = PluginInstance(
                plugin_key=manifest.name,
                name=manifest.name,
                type=manifest.type,
                version=manifest.version,
                source="builtin",
                manifest=manifest.model_dump(),
                config={},
                enabled=True,
            )
            session.add(row)
            added += 1
        if added > 0:
            await session.commit()
            logger.info("plugin builtin seeded | count={}", added)
        return added


plugin_registry = PluginRegistry()
