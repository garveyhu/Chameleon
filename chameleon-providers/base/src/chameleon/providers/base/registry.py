"""Provider + Agent 注册表构建

启动时执行一次，运行时只读。
fail-fast：重复 key / 占位符未解析 / yaml 引用未注册的 provider —— 全报错退出。

两个全局 dict：
  PROVIDERS: dict[str, Provider]
  AGENTS:    dict[str, AgentDef]
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from chameleon.core.config.base_settings import (
    ConfigError,
    _resolve_placeholders,
    make_default_resolver,
)
from chameleon.core.config.constants import CONFIG_PATH
from chameleon.core.config.json_settings import url_settings
from chameleon.core.exceptions import RegistryError
from chameleon.providers.base.protocol import Provider
from chameleon.providers.base.types import AgentDef

PROVIDERS: dict[str, Provider] = {}
AGENTS: dict[str, AgentDef] = {}

_BUILT = False


# ── Provider 注册（扫 chameleon.providers.* namespace） ─────


def build_provider_registry() -> dict[str, Provider]:
    """扫 chameleon.providers.* namespace，找到每个子包的 PROVIDER 实例

    base 子包跳过；其它每个子包 __init__.py 必须 export PROVIDER。
    """
    import chameleon.providers as pkg

    providers: dict[str, Provider] = {}
    for mod_info in pkgutil.iter_modules(pkg.__path__, "chameleon.providers."):
        # base 自身不是 provider 实现
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
        if provider.name in providers:
            raise RegistryError(message=f"duplicate provider name: {provider.name}")
        providers[provider.name] = provider
        logger.info(
            "provider registered | name={} | from={}", provider.name, mod_info.name
        )

    # 向后兼容 alias：v0.1 的本地 agent 用 provider="langgraph"，现在 → "local"
    if "local" in providers and "langgraph" not in providers:
        providers["langgraph"] = providers["local"]
        logger.debug("provider alias | langgraph → local（v0.1 向后兼容）")

    return providers


# ── Agent 注册（namespace 扫 + yaml 读，双源合并） ─────────


def _build_local_agents() -> dict[str, AgentDef]:
    """扫 chameleon.agents.* namespace，每个子包必须 export AGENT_META + build_graph"""
    try:
        import chameleon.agents as pkg
    except ImportError:
        # 没有任何 agent 子包安装也允许（极端情况）
        logger.warning("chameleon.agents namespace not found — no local agents")
        return {}

    agents: dict[str, AgentDef] = {}
    for mod_info in pkgutil.iter_modules(pkg.__path__, "chameleon.agents."):
        try:
            mod = importlib.import_module(mod_info.name)
        except Exception as e:
            raise RegistryError(
                message=f"failed to import agent package {mod_info.name}: {e}"
            ) from e

        # 本地 agent 统一一种范式：BaseAgent 子类
        # （v0.2 删了字典模式 AGENT_META + build_graph，强制 BaseAgent 子类）
        agent_cls = _find_base_agent_class(mod)
        if agent_cls is None:
            # 没找到 BaseAgent 子类 —— 跳过（视为占位空包）
            logger.debug(
                "agent package {} has no BaseAgent subclass — skipped",
                mod_info.name,
            )
            continue

        md = agent_cls.get_metadata()
        key = md.id
        if not key:
            raise RegistryError(
                message=f"{agent_cls.__name__}.get_metadata().id 不能为空"
            )

        agents[key] = AgentDef(
            key=key,
            provider="local",
            description=md.description,
            version=md.version,
            tags=list(md.tags),
            config={
                "module": mod_info.name,
                "agent_class": agent_cls.__name__,
            },
        )
        logger.info(
            "agent registered (local) | key={} | class={} | module={}",
            key,
            agent_cls.__name__,
            mod_info.name,
        )

        # 同时注册到 agent_router（给 v0.2 admin UI 用）
        try:
            from chameleon.core.base.agent_router import agent_router

            agent_router.register(agent_cls)
        except Exception as e:
            logger.warning("agent_router.register failed for {}: {}", key, e)

    return agents


def _find_base_agent_class(module):
    """在模块的顶层符号里找一个 BaseAgent 子类。约定：同一模块至多一个。"""
    try:
        from chameleon.core.base.base_agent import BaseAgent
    except ImportError:
        return None

    for name in dir(module):
        obj = getattr(module, name, None)
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseAgent)
            and obj is not BaseAgent
            and obj.__module__.startswith(module.__name__)
        ):
            return obj
    return None


def _build_yaml_agents(yaml_path: Path) -> dict[str, AgentDef]:
    """读 config/agents.yaml，按 provider 字段注册外部 agent"""
    if not yaml_path.exists():
        logger.warning("agents.yaml not found at {} — no external agents", yaml_path)
        return {}

    with open(yaml_path, encoding="utf-8") as f:
        raw: Any = yaml.safe_load(f)
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise RegistryError(
            message=f"agents.yaml must be a list, got {type(raw).__name__}"
        )

    # 占位符替换
    resolver = make_default_resolver(baseurl_lookup=lambda k: url_settings.get(k))
    try:
        resolved = _resolve_placeholders(raw, resolver)
    except ConfigError as e:
        raise RegistryError(message=f"agents.yaml placeholder error: {e}") from e

    agents: dict[str, AgentDef] = {}
    for i, entry in enumerate(resolved):
        if not isinstance(entry, dict):
            raise RegistryError(message=f"agents.yaml entry #{i} must be a dict")
        key = entry.get("key")
        provider = entry.get("provider")
        if not key or not provider:
            raise RegistryError(
                message=f"agents.yaml entry #{i} missing 'key' or 'provider'"
            )
        config = {
            k: v
            for k, v in entry.items()
            if k not in {"key", "provider", "description", "version", "tags"}
        }
        agents[key] = AgentDef(
            key=key,
            provider=provider,
            description=entry.get("description", ""),
            version=entry.get("version"),
            tags=entry.get("tags", []),
            config=config,
        )
        logger.info("agent registered (yaml) | key={} | provider={}", key, provider)
    return agents


def build_agent_registry(
    providers: dict[str, Provider],
    yaml_path: Path | None = None,
) -> dict[str, AgentDef]:
    """合并本地 + yaml，校验：provider 必须已注册；agent key 不可重复"""
    if yaml_path is None:
        yaml_path = CONFIG_PATH / "agents.yaml"

    local = _build_local_agents()
    yaml_agents = _build_yaml_agents(yaml_path)

    duplicates = set(local) & set(yaml_agents)
    if duplicates:
        raise RegistryError(
            message=f"agent key conflict (both local + yaml): {sorted(duplicates)}"
        )

    merged: dict[str, AgentDef] = {**local, **yaml_agents}

    # 校验 provider 已注册
    unknown_providers = {
        agent.provider for agent in merged.values() if agent.provider not in providers
    }
    if unknown_providers:
        raise RegistryError(
            message=f"agents reference unregistered providers: {sorted(unknown_providers)}"
        )

    return merged


# ── 启动钩子 ────────────────────────────────────────────


def init_registry(yaml_path: Path | None = None) -> None:
    """一次性构建全局 PROVIDERS / AGENTS"""
    global _BUILT
    if _BUILT:
        logger.debug("registry already built — skip")
        return

    PROVIDERS.clear()
    PROVIDERS.update(build_provider_registry())

    AGENTS.clear()
    AGENTS.update(build_agent_registry(PROVIDERS, yaml_path=yaml_path))

    _BUILT = True

    logger.info(
        "registry built | providers={} | agents={}",
        list(PROVIDERS.keys()),
        list(AGENTS.keys()),
    )


def reset_registry_for_test() -> None:
    """测试用：重置 built 标记"""
    global _BUILT
    PROVIDERS.clear()
    AGENTS.clear()
    _BUILT = False
