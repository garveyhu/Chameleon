"""Provider + Agent 注册表构建（v0.2 DB-driven）

启动期 async 流程：
  1. PROVIDERS：扫 chameleon.providers.* namespace，收 Provider 实例（不变）
  2. namespace 扫 chameleon.agents.* import 模块（让 BaseAgent 子类落 agent_router）
  3. AGENTS：从 DB agents 表（enabled=True, deleted_at IS NULL）读

业务热路径只读 AGENTS / PROVIDERS 两个 dict。
admin 改 agent enabled / 加新外部 agent 后，调 reload_agent_registry() 让 dict 更新。
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

from loguru import logger
from sqlalchemy import select

from chameleon.core.api.exceptions import RegistryError
from chameleon.core.models import Agent
from chameleon.providers.base.protocol import Provider
from chameleon.providers.base.types import AgentDef

PROVIDERS: dict[str, Provider] = {}
AGENTS: dict[str, AgentDef] = {}

_BUILT = False


# ── Provider 注册（扫 chameleon.providers.* namespace） ─────


def build_provider_registry(
    disabled_plugin_keys: set[str] | None = None,
) -> dict[str, Provider]:
    """扫 chameleon.providers.* namespace 找每个子包的 PROVIDER 实例

    Args:
        disabled_plugin_keys: 由 PluginRegistry 提供的禁用集（P19.2）；
            匹配到的 provider.name 会被跳过，实现"不重启进程禁用 builtin plugin"
    """
    import chameleon.providers as pkg

    disabled = disabled_plugin_keys or set()
    providers: dict[str, Provider] = {}
    for mod_info in pkgutil.iter_modules(pkg.__path__, "chameleon.providers."):
        if mod_info.name.endswith(".base"):
            continue
        try:
            mod = importlib.import_module(mod_info.name)
        except Exception as e:
            raise RegistryError(
                message=f"failed to import provider package {mod_info.name}: {e}"
            ) from e

        provider = getattr(mod, "PROVIDER", None)
        if provider is None:
            logger.warning(
                "provider package {} has no PROVIDER export — skipped", mod_info.name
            )
            continue
        if not isinstance(provider, Provider):
            raise RegistryError(
                message=f"{mod_info.name}.PROVIDER is not a Provider instance"
            )
        if provider.name in disabled:
            logger.info(
                "provider skipped (plugin disabled) | name={} | from={}",
                provider.name,
                mod_info.name,
            )
            continue
        if provider.name in providers:
            raise RegistryError(message=f"duplicate provider name: {provider.name}")
        providers[provider.name] = provider
        logger.info(
            "provider registered | name={} | from={}", provider.name, mod_info.name
        )

    return providers


# ── namespace 扫 chameleon.agents.* import 加载 BaseAgent 类 ─


def _scan_local_agent_modules() -> dict[str, type]:
    """扫 chameleon.agents.* 子包，import + 找 BaseAgent 子类

    Returns:
        {agent_key: agent_class}（提供给 AGENTS config["module"]/["agent_class"] fallback）
    """
    try:
        import chameleon.agents as pkg
    except ImportError:
        logger.warning("chameleon.agents namespace not found — no local agents")
        return {}

    from chameleon.core.base.agent_router import agent_router
    from chameleon.core.base.base_agent import BaseAgent

    found: dict[str, type] = {}
    for mod_info in pkgutil.iter_modules(pkg.__path__, "chameleon.agents."):
        try:
            mod = importlib.import_module(mod_info.name)
        except Exception as e:
            raise RegistryError(
                message=f"failed to import agent package {mod_info.name}: {e}"
            ) from e
        agent_cls = _find_base_agent_class(mod, BaseAgent)
        if agent_cls is None:
            continue
        meta = agent_cls.get_metadata()
        if not meta.id:
            raise RegistryError(
                message=f"{agent_cls.__name__}.get_metadata().id 不能为空"
            )
        found[meta.id] = agent_cls
        try:
            agent_router.register(agent_cls)
        except Exception as e:
            logger.warning("agent_router.register failed for {}: {}", meta.id, e)
    return found


def _find_base_agent_class(module: Any, base_cls: type) -> type | None:
    for name in dir(module):
        obj = getattr(module, name, None)
        if (
            isinstance(obj, type)
            and issubclass(obj, base_cls)
            and obj is not base_cls
            and obj.__module__.startswith(module.__name__)
        ):
            return obj
    return None


# ── Agent 注册（DB 读，agents 表是 SoT） ──────────────────


async def build_agent_registry_from_db(
    providers: dict[str, Provider],
    *,
    local_class_index: dict[str, type] | None = None,
) -> dict[str, AgentDef]:
    """从 DB agents 表 + namespace import 结果合并产 AGENTS dict

    Args:
        providers: 已经 build 好的 PROVIDERS dict（用于校验 agent.source 存在）
        local_class_index: namespace 扫到的 {agent_key: class}；DB 里 source='local'
                          但 class 不在索引里时 → 跳过并 warn（agent 安装包未装）

    DB 里的 source 字段映射 provider name：
      'local' → providers["local"]
      'dify'  → providers["dify"]
      ...
    """
    from chameleon.core.infra.db import AsyncSessionLocal

    if local_class_index is None:
        local_class_index = {}

    async with AsyncSessionLocal() as session:
        rows = (
            (
                await session.execute(
                    select(Agent).where(
                        Agent.enabled.is_(True),
                        Agent.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )

    agents: dict[str, AgentDef] = {}
    for row in rows:
        provider_name = row.source
        if provider_name not in providers:
            logger.warning(
                "agent {} 引用未注册 provider {} —— 跳过",
                row.agent_key,
                provider_name,
            )
            continue

        # 本地 agent：class 必须能从 namespace 扫到
        if provider_name == "local" and row.agent_key not in local_class_index:
            logger.warning(
                "本地 agent {} 在 DB 中 enabled，但 chameleon.agents.* 未发现对应 class — 跳过",
                row.agent_key,
            )
            continue

        agents[row.agent_key] = AgentDef(
            key=row.agent_key,
            provider=provider_name,
            description=row.description or "",
            version=row.version,
            tags=list(row.tags) if row.tags else [],
            config=dict(row.config) if row.config else {},
        )
        logger.info(
            "agent registered (db) | key={} | provider={} | enabled=True",
            row.agent_key,
            provider_name,
        )
    return agents


# ── 启动钩子 ────────────────────────────────────────────


async def init_registry() -> None:
    """启动期入口（async）：build providers + 扫本地 import + DB 读 agents

    P19.2：先 seed builtin plugin + 拉 disabled 集，对应 provider 不挂载
    """
    global _BUILT
    if _BUILT:
        logger.debug("registry already built — skip")
        return

    # Plugin bootstrap：seed builtin manifest + 获取 provider 维度禁用集
    disabled_provider_keys: set[str] = set()
    try:
        from chameleon.core.infra.db import AsyncSessionLocal
        from chameleon.core.plugins import plugin_registry
        from chameleon.core.plugins.builtins import BUILTIN_PROVIDERS

        async with AsyncSessionLocal() as s:
            await plugin_registry.bootstrap_builtin(s, BUILTIN_PROVIDERS)
            disabled_provider_keys = await plugin_registry.disabled_keys_for_type(
                s, "provider"
            )
    except Exception as e:  # noqa: BLE001
        # 老库可能还没 p19_w19_plugins 表 / DB 不可用 → 跳过 plugin 层，回到原行为
        logger.warning(
            "plugin bootstrap skipped (DB / migration not ready?): {}", e
        )

    PROVIDERS.clear()
    PROVIDERS.update(build_provider_registry(disabled_provider_keys))

    local_class_index = _scan_local_agent_modules()

    AGENTS.clear()
    AGENTS.update(
        await build_agent_registry_from_db(
            PROVIDERS, local_class_index=local_class_index
        )
    )

    _BUILT = True

    logger.info(
        "registry built | providers={} | agents={}",
        list(PROVIDERS.keys()),
        list(AGENTS.keys()),
    )


async def reload_agent_registry() -> None:
    """admin 改 agents 表（enable/disable/add 外部）后调，让 AGENTS 更新

    幂等；不重 import namespace（重复 import 副作用小，但慢）。
    """
    local_class_index = _scan_local_agent_modules()
    new_agents = await build_agent_registry_from_db(
        PROVIDERS, local_class_index=local_class_index
    )
    AGENTS.clear()
    AGENTS.update(new_agents)
    logger.info("agent registry reloaded | agents={}", list(AGENTS.keys()))


def reset_registry_for_test() -> None:
    """测试用：重置 built 标记 + 清空 dict"""
    global _BUILT
    PROVIDERS.clear()
    AGENTS.clear()
    _BUILT = False
