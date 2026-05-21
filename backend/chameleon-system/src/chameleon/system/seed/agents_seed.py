"""agents seed：本地 namespace 扫描 + agents.yaml 外部条目

本地 agent：扫 chameleon.agents.* namespace 找 BaseAgent 子类，source='local'
外部 agent：读 config/agents.yaml，source=provider 字段（dify / fastgpt 等）

幂等：已存在 agent_key 跳过。
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any

import yaml
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.config.constants import CONFIG_PATH
from chameleon.core.models import Agent


async def seed_agents(
    session: AsyncSession,
    *,
    config_dir: Path | None = None,
) -> None:
    existing_keys = set(
        (await session.execute(select(Agent.agent_key))).scalars().all()
    )

    await _seed_local_agents(session, existing_keys)
    await _seed_external_from_yaml(session, existing_keys, config_dir=config_dir)


# ── 本地 agents（namespace 扫描） ─────────────────────────


async def _seed_local_agents(
    session: AsyncSession,
    existing_keys: set[str],
) -> None:
    try:
        import chameleon.agents as pkg
    except ImportError:
        logger.warning("seed: chameleon.agents namespace 不存在，跳过本地 agent")
        return

    from chameleon.core.base.base_agent import BaseAgent

    inserted = 0
    for mod_info in pkgutil.iter_modules(pkg.__path__, "chameleon.agents."):
        try:
            mod = importlib.import_module(mod_info.name)
        except Exception as e:
            logger.warning("seed: import {} 失败 {}", mod_info.name, e)
            continue

        agent_cls = _find_base_agent_class(mod, BaseAgent)
        if agent_cls is None:
            continue

        meta = agent_cls.get_metadata()
        if not meta.id or meta.id in existing_keys:
            continue

        session.add(
            Agent(
                agent_key=meta.id,
                name=meta.name,
                description=meta.description,
                source="local",
                local_class_path=f"{agent_cls.__module__}.{agent_cls.__name__}",
                config={"module": mod_info.name, "agent_class": agent_cls.__name__},
                tags=list(meta.tags) if meta.tags else None,
                enabled=True,
                version=meta.version,
            )
        )
        existing_keys.add(meta.id)
        inserted += 1
        logger.info("seed: local agent {} → {}", meta.id, agent_cls.__name__)
    if inserted:
        await session.flush()
    logger.info("seed: local agents ({})", inserted)


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


# ── 外部 agents（agents.yaml） ─────────────────────────────


async def _seed_external_from_yaml(
    session: AsyncSession,
    existing_keys: set[str],
    *,
    config_dir: Path | None = None,
) -> None:
    yaml_path = (config_dir or CONFIG_PATH) / "agents.yaml"
    if not yaml_path.exists():
        logger.debug("seed: {} 不存在，跳过外部 agent", yaml_path)
        return

    with open(yaml_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not raw:
        return
    if not isinstance(raw, list):
        logger.warning("seed: agents.yaml 顶层应为 list，跳过")
        return

    inserted = 0
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            logger.warning("seed: agents.yaml entry #{} 非 dict 跳过", i)
            continue
        agent_key = entry.get("key")
        provider = entry.get("provider")
        if not agent_key or not provider:
            logger.warning("seed: agents.yaml entry #{} 缺 key/provider 跳过", i)
            continue
        if agent_key in existing_keys:
            continue

        config = {
            k: v
            for k, v in entry.items()
            if k not in {"key", "provider", "description", "name", "version", "tags"}
        }
        session.add(
            Agent(
                agent_key=agent_key,
                name=entry.get("name") or agent_key,
                description=entry.get("description"),
                source=provider,
                config=config or None,
                tags=entry.get("tags"),
                enabled=True,
                version=entry.get("version"),
            )
        )
        existing_keys.add(agent_key)
        inserted += 1
        logger.info("seed: external agent {} ({})", agent_key, provider)
    if inserted:
        await session.flush()
    logger.info("seed: external agents ({})", inserted)
