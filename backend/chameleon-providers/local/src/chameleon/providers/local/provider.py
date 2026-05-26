"""LocalProvider —— Chameleon 本地 in-process provider

调本地（in-process）agent，不发任何 HTTP 请求。
所有本地 agent 必须是 `BaseAgent` 子类，实现 `astream(ctx)` async generator。

内部实现框架自由（agent 作者自选）：
- 纯 Python async generator（最自由）
- LangChain Runnable / LCEL（用 from_runnable 桥）
- LangGraph CompiledGraph（用 from_langgraph_graph 桥）
- 三者混合

★ 与 "remote" provider（dify / fastgpt）的本质区别：
   - local：进程内调用，零网络 IO，毫秒级；
   - remote：HTTP 远调外部 SaaS 平台，网络抖动 + 鉴权 + 限流要兜底。
"""

from __future__ import annotations

import importlib
from collections.abc import AsyncIterator

from loguru import logger

from chameleon.core.api.exceptions import ProviderInternalError, RegistryError
from chameleon.providers.base.protocol import Provider
from chameleon.providers.base.types import InvokeContext, StreamEvent
from chameleon.providers.local.agentkit_runner import is_agentkit_agent, run_agentkit


class LocalProvider(Provider):
    """本地 in-process provider

    provider name = "local"（agents.yaml + AgentDef 用）
    """

    name = "local"

    async def stream(self, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        cfg = ctx.agent_def.config

        # agentkit @agent 智能体：走 ctx-based runner（registry build 注入定位标记）
        if is_agentkit_agent(ctx):
            try:
                async for ev in run_agentkit(ctx):
                    yield ev
            except Exception as e:
                if "Provider" in type(e).__name__:
                    raise
                if type(e).__name__.endswith("Error") and "Business" in type(e).__name__:
                    raise
                raise ProviderInternalError(
                    message=f"agentkit agent {ctx.agent_def.key} 运行失败: {e}"
                ) from e
            return

        module_path = cfg.get("module")
        agent_cls_name = cfg.get("agent_class")
        if not module_path or not agent_cls_name:
            raise RegistryError(
                message=(
                    f"local agent {ctx.agent_def.key} 缺 config.module / "
                    "config.agent_class（请用 BaseAgent 子类范式）"
                )
            )

        try:
            mod = importlib.import_module(module_path)
        except Exception as e:
            raise RegistryError(message=f"failed to import {module_path}: {e}") from e

        agent_cls = getattr(mod, agent_cls_name, None)
        if agent_cls is None:
            raise RegistryError(message=f"{module_path}.{agent_cls_name} not found")

        logger.debug("local provider | agent={}", ctx.agent_def.key)
        try:
            async for ev in agent_cls.astream(ctx):
                yield ev
        except Exception as e:
            # 让 BusinessError / ProviderError 等业务异常透传（全局 handler 接管）
            if "ProviderError" in type(e).__name__ or "Provider" in type(e).__name__:
                raise
            if type(e).__name__.endswith("Error") and "Business" in type(e).__name__:
                raise
            raise ProviderInternalError(
                message=f"local agent {ctx.agent_def.key} astream failed: {e}"
            ) from e

    async def healthcheck(self) -> bool:
        return True
