"""LangGraph 编译产物缓存

裁决 A4：build_graph() 是 sync function。
首次 invoke 时构建 + 缓存，后续直接拿用。用 asyncio.Lock 保护并发首建。
"""

from __future__ import annotations

import asyncio
import importlib
from typing import Any

from loguru import logger

from chameleon.core.exceptions import RegistryError
from chameleon.providers.base.types import AgentDef


class GraphBuilder:
    """{agent_key: compiled_graph} 单例缓存"""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        # 每个 key 一把锁，避免首次并发重复构建
        self._locks: dict[str, asyncio.Lock] = {}
        self._dict_lock = asyncio.Lock()

    async def get_or_build(self, agent_def: AgentDef) -> Any:
        cached = self._cache.get(agent_def.key)
        if cached is not None:
            return cached

        # 取/建该 key 的锁
        async with self._dict_lock:
            lock = self._locks.setdefault(agent_def.key, asyncio.Lock())

        async with lock:
            # double-check
            cached = self._cache.get(agent_def.key)
            if cached is not None:
                return cached

            graph = self._build(agent_def)
            self._cache[agent_def.key] = graph
            logger.info(
                "langgraph compiled | agent={} | module={}",
                agent_def.key,
                agent_def.config.get("module"),
            )
            return graph

    def _build(self, agent_def: AgentDef) -> Any:
        module_path = agent_def.config.get("module")
        build_fn_name = agent_def.config.get("build_fn", "build_graph")
        if not module_path:
            raise RegistryError(message=f"agent {agent_def.key} missing config.module")
        try:
            mod = importlib.import_module(module_path)
        except Exception as e:
            raise RegistryError(message=f"failed to import {module_path}: {e}") from e

        build_fn = getattr(mod, build_fn_name, None)
        if build_fn is None:
            raise RegistryError(message=f"{module_path}.{build_fn_name} not found")
        try:
            return build_fn()
        except Exception as e:
            raise RegistryError(
                message=f"{module_path}.{build_fn_name}() failed: {e}"
            ) from e

    def clear_for_test(self) -> None:
        self._cache.clear()
        self._locks.clear()
