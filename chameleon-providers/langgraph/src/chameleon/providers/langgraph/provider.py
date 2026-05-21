"""本地 in-process Provider —— 统一调用本地 agent

★ v0.1.x 重大重构：从"只支持 LangGraph"→"本地 agent 框架不限制"

支持的 agent 形态（**registry 启动时自动识别**）：

1. **BaseAgent 子类（推荐）**：实现 `astream(ctx)` async generator
   - 内部可以用 LangGraph / LangChain / 纯 Python / 混合
   - 通过 `from chameleon.core.base.bridges import ...` 桥工具用 LangGraph/Runnable

2. **字典模式（兼容现有 echo 等）**：模块顶层 `AGENT_META + build_graph` 函数
   - LocalProvider 走 langgraph 桥（与 v0.1 行为一致）

3. **build_runnable() 字典模式**：模块顶层 `AGENT_META + build_runnable` 函数
   - LocalProvider 走 langchain 桥

provider name 保留为 "langgraph"——向后兼容 agents.yaml 与现有 ORM 数据。
未来若有 v0.2 admin UI 需要更准确命名，再加 "local" alias。
"""

from __future__ import annotations

import importlib
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from chameleon.core.exceptions import ProviderInternalError, RegistryError
from chameleon.providers.base.protocol import Provider
from chameleon.providers.base.types import InvokeContext, StreamEvent


class LangGraphProvider(Provider):
    """本地 in-process provider（保留命名兼容 v0.1）"""

    name = "langgraph"

    async def stream(self, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        cfg = ctx.agent_def.config
        module_path = cfg.get("module")
        if not module_path:
            raise RegistryError(
                message=f"agent {ctx.agent_def.key} missing config.module"
            )

        try:
            mod = importlib.import_module(module_path)
        except Exception as e:
            raise RegistryError(message=f"failed to import {module_path}: {e}") from e

        # ── 路径 1：BaseAgent 子类 → 调 cls.astream() ─────
        agent_cls_name = cfg.get("agent_class")
        if agent_cls_name:
            agent_cls = getattr(mod, agent_cls_name, None)
            if agent_cls is None:
                raise RegistryError(message=f"{module_path}.{agent_cls_name} not found")
            logger.debug(
                "local provider | agent={} | mode=BaseAgent.astream",
                ctx.agent_def.key,
            )
            try:
                async for ev in agent_cls.astream(ctx):
                    yield ev
            except Exception as e:
                if (
                    "ProviderError" in type(e).__name__
                    or "Provider" in type(e).__name__
                ):
                    raise
                raise ProviderInternalError(
                    message=f"local agent {ctx.agent_def.key} astream failed: {e}"
                ) from e
            return

        # ── 路径 2：字典模式 build_graph（v0.1 兼容） ──────
        if hasattr(mod, "build_graph"):
            from chameleon.core.base.bridges import astream_from_langgraph_graph

            logger.debug(
                "local provider | agent={} | mode=build_graph(dict)",
                ctx.agent_def.key,
            )
            graph = _get_or_build_dict_graph(ctx.agent_def.key, mod)
            try:
                async for ev in astream_from_langgraph_graph(ctx, graph):
                    yield ev
            except Exception as e:
                if "ProviderError" in type(e).__name__:
                    raise
                raise ProviderInternalError(
                    message=f"langgraph runtime error: {e}"
                ) from e
            return

        # ── 路径 3：字典模式 build_runnable ────────────────
        if hasattr(mod, "build_runnable"):
            from chameleon.core.base.bridges import astream_from_runnable

            logger.debug(
                "local provider | agent={} | mode=build_runnable(dict)",
                ctx.agent_def.key,
            )
            runnable = _get_or_build_dict_runnable(ctx.agent_def.key, mod)
            try:
                async for ev in astream_from_runnable(ctx, runnable):
                    yield ev
            except Exception as e:
                if "ProviderError" in type(e).__name__:
                    raise
                raise ProviderInternalError(
                    message=f"runnable runtime error: {e}"
                ) from e
            return

        raise RegistryError(
            message=(
                f"local agent {ctx.agent_def.key} ({module_path}) provides none of: "
                "BaseAgent subclass / build_graph() / build_runnable()"
            )
        )

    async def healthcheck(self) -> bool:
        return True


# ── 字典模式产物缓存（v0.1 兼容路径） ────────────────────


_dict_graph_cache: dict[str, Any] = {}
_dict_runnable_cache: dict[str, Any] = {}


def _get_or_build_dict_graph(key: str, mod: Any) -> Any:
    cached = _dict_graph_cache.get(key)
    if cached is not None:
        return cached
    try:
        graph = mod.build_graph()
    except Exception as e:
        raise RegistryError(message=f"{mod.__name__}.build_graph() failed: {e}") from e
    _dict_graph_cache[key] = graph
    logger.info("local langgraph compiled (dict mode) | agent={}", key)
    return graph


def _get_or_build_dict_runnable(key: str, mod: Any) -> Any:
    cached = _dict_runnable_cache.get(key)
    if cached is not None:
        return cached
    try:
        runnable = mod.build_runnable()
    except Exception as e:
        raise RegistryError(
            message=f"{mod.__name__}.build_runnable() failed: {e}"
        ) from e
    _dict_runnable_cache[key] = runnable
    logger.info("local runnable built (dict mode) | agent={}", key)
    return runnable


def _clear_caches_for_test() -> None:
    _dict_graph_cache.clear()
    _dict_runnable_cache.clear()
