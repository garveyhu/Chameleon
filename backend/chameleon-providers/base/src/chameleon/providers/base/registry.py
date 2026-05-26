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


def _scan_local_agent_modules() -> tuple[dict[str, type], dict[str, Any]]:
    """扫 chameleon.agents.* 子包，找 BaseAgent 子类 + @agent 声明（agentkit）。

    Returns:
        (base_index, agentkit_index)
        - base_index:     {agent_key: BaseAgent 子类}（老范式）
        - agentkit_index: {agent_key: @agent 目标（函数 / 类）}（agentkit 新范式）
    """
    try:
        import chameleon.agents as pkg
    except ImportError:
        logger.warning("chameleon.agents namespace not found — no local agents")
        return {}, {}

    from chameleon.core.base.agent_router import agent_router
    from chameleon.core.base.base_agent import BaseAgent

    base_index: dict[str, type] = {}
    agentkit_index: dict[str, Any] = {}
    for mod_info in pkgutil.iter_modules(pkg.__path__, "chameleon.agents."):
        try:
            mod = importlib.import_module(mod_info.name)
        except Exception as e:
            raise RegistryError(
                message=f"failed to import agent package {mod_info.name}: {e}"
            ) from e
        # ① BaseAgent 子类（老范式）
        agent_cls = _find_base_agent_class(mod, BaseAgent)
        if agent_cls is not None:
            meta = agent_cls.get_metadata()
            if not meta.id:
                raise RegistryError(
                    message=f"{agent_cls.__name__}.get_metadata().id 不能为空"
                )
            base_index[meta.id] = agent_cls
            try:
                agent_router.register(agent_cls)
            except Exception as e:
                logger.warning("agent_router.register failed for {}: {}", meta.id, e)
        # ② @agent 声明（agentkit 新范式，函数 / 类）
        for tgt in _find_agentkit_targets(mod):
            agentkit_index[tgt.__agent_manifest__.key] = tgt
    return base_index, agentkit_index


def _find_agentkit_targets(module: Any) -> list[Any]:
    """找 module 里本包定义的 @agent 目标（带 __agent_manifest__）。"""
    out: list[Any] = []
    seen: set[int] = set()
    for name in dir(module):
        obj = getattr(module, name, None)
        if getattr(obj, "__agent_manifest__", None) is None:
            continue
        if not getattr(obj, "__module__", "").startswith(module.__name__):
            continue
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        out.append(obj)
    return out


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
    agentkit_index: dict[str, Any] | None = None,
) -> dict[str, AgentDef]:
    """从 DB agents 表 + namespace import 结果合并产 AGENTS dict

    Args:
        providers: 已经 build 好的 PROVIDERS dict（用于校验 agent.source 存在）
        local_class_index: namespace 扫到的 BaseAgent {agent_key: class}
        agentkit_index: namespace 扫到的 @agent {agent_key: 目标}；命中则注入
                        定位标记 + model_bindings，运行时走 agentkit runner
                        （source='local' 但两索引都没有 → 跳过并 warn）

    DB 里的 source 字段映射 provider name：
      'local' → providers["local"]
      'dify'  → providers["dify"]
      'graph' → providers["graph"]（config 预载该 graph 的 published_spec）
      ...
    """
    from chameleon.core.infra.db import AsyncSessionLocal
    from chameleon.core.models import Graph

    if local_class_index is None:
        local_class_index = {}
    if agentkit_index is None:
        agentkit_index = {}

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

        # graph agent：预载关联 graph 的 published_spec（运行时 GraphProvider 用，
        # invoke 时不再碰 DB）。只取已发布的；未发布的 agent 后续跳过。
        graph_ids = {
            r.graph_id for r in rows if r.source == "graph" and r.graph_id
        }
        graph_specs: dict[int, dict] = {}
        if graph_ids:
            grows = (
                (await session.execute(select(Graph).where(Graph.id.in_(graph_ids))))
                .scalars()
                .all()
            )
            for g in grows:
                if g.published_spec:
                    graph_specs[g.id] = g.published_spec

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

        # 本地 agent：BaseAgent 子类或 @agent 声明，至少命中一个索引
        if (
            provider_name == "local"
            and row.agent_key not in local_class_index
            and row.agent_key not in agentkit_index
        ):
            logger.warning(
                "本地 agent {} 在 DB 中 enabled，但 chameleon.agents.* 未发现对应 class / @agent — 跳过",
                row.agent_key,
            )
            continue

        config = dict(row.config) if row.config else {}
        # graph agent：config 收敛成 {graph_id, spec}（published_spec）
        if provider_name == "graph":
            spec = graph_specs.get(row.graph_id) if row.graph_id else None
            if spec is None:
                logger.warning(
                    "graph agent {} 无 published_spec（未发布 / graph 已删）— 跳过",
                    row.agent_key,
                )
                continue
            config = {"graph_id": row.graph_id, "spec": spec}
        # agentkit @agent：注入定位标记 + 多槽模型绑定（运行时走 agentkit runner）
        elif provider_name == "local" and row.agent_key in agentkit_index:
            tgt = agentkit_index[row.agent_key]
            config["__agentkit_module__"] = tgt.__module__
            config["__agentkit_attr__"] = tgt.__name__
            config["model_bindings"] = (
                dict(row.model_bindings) if row.model_bindings else {}
            )

        agents[row.agent_key] = AgentDef(
            key=row.agent_key,
            provider=provider_name,
            description=row.description or "",
            version=row.version,
            tags=list(row.tags) if row.tags else [],
            config=config,
        )
        logger.info(
            "agent registered (db) | key={} | provider={} | enabled=True",
            row.agent_key,
            provider_name,
        )
    return agents


# ── 启动钩子 ────────────────────────────────────────────


async def sync_local_agents_to_db(
    base_index: dict[str, type],
    agentkit_index: dict[str, Any],
) -> None:
    """本地 agent 以**代码为准**，启动期对账 DB（仅 source='local'）：

    - 代码声明但 DB 无 → 新建 enabled 行（@agent / BaseAgent 都覆盖）
    - DB 有但代码已删 → 逻辑删除（deleted_at + 改名释放 agent_key + disable）

    其他来源（graph / dify / fastgpt）不受影响。import 失败会在扫描阶段直接抛错、
    不会走到这里，所以"代码不在索引"即真删除信号，可安全逻辑删。
    """
    from datetime import datetime, timezone

    from chameleon.core.infra.db import AsyncSessionLocal
    from chameleon.core.models import Agent

    code_keys = set(base_index) | set(agentkit_index)

    async with AsyncSessionLocal() as session:
        rows = (
            (
                await session.execute(
                    select(Agent).where(
                        Agent.source == "local", Agent.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        db_keys = {r.agent_key for r in rows}

        removed = 0
        for r in rows:
            if r.agent_key not in code_keys:
                r.deleted_at = datetime.now(timezone.utc)
                r.enabled = False
                r.agent_key = f"__deleted_{r.id}_{r.agent_key}"
                removed += 1

        created = 0
        for key in code_keys - db_keys:
            if key in agentkit_index:
                tgt = agentkit_index[key]
                m = tgt.__agent_manifest__
                session.add(
                    Agent(
                        agent_key=key,
                        name=m.name,
                        description=m.description,
                        source="local",
                        local_class_path=f"{tgt.__module__}.{tgt.__name__}",
                        config={},
                        tags=list(m.tags) if m.tags else None,
                        enabled=True,
                    )
                )
            else:
                cls = base_index[key]
                meta = cls.get_metadata()
                session.add(
                    Agent(
                        agent_key=key,
                        name=meta.name,
                        description=meta.description,
                        source="local",
                        local_class_path=f"{cls.__module__}.{cls.__name__}",
                        config={"module": cls.__module__, "agent_class": cls.__name__},
                        tags=list(meta.tags) if meta.tags else None,
                        enabled=True,
                        version=meta.version,
                    )
                )
            created += 1

        if removed or created:
            await session.commit()
            logger.info(
                "local agent 对账 | 新建={} | 逻辑删除={}", created, removed
            )


async def init_registry() -> None:
    """启动期入口（async）：build providers + 扫本地 import + 对账 + DB 读 agents

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

    local_class_index, agentkit_index = _scan_local_agent_modules()

    # 本地 agent 以代码为准：对账 DB（新增建行 / 删码逻辑删）
    await sync_local_agents_to_db(local_class_index, agentkit_index)

    AGENTS.clear()
    AGENTS.update(
        await build_agent_registry_from_db(
            PROVIDERS,
            local_class_index=local_class_index,
            agentkit_index=agentkit_index,
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
    local_class_index, agentkit_index = _scan_local_agent_modules()
    new_agents = await build_agent_registry_from_db(
        PROVIDERS,
        local_class_index=local_class_index,
        agentkit_index=agentkit_index,
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
