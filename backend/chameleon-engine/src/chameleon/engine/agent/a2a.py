"""A2A（Agent-to-Agent）协议 + AgentRunner —— P20.4 PR #55

跨 agent 调用统一入口。底层走 PROVIDERS / AGENTS 注册表 +
chameleon.core.observe.context 嵌套上下文管理器，自动串 observation tree。

红线：
- ⛔ trace_id 必须传 —— 不传直接抛 ValidationError；observation 必须挂在
  trace tree 上，不可断链
- ⛔ budget_remaining > 0 —— A2A 调用前预算检查，0 或负值拒绝；防 agents
  互相调用 token 无限爆
- ⛔ depth < MAX_DEPTH (=3) —— 跨 agent 调用嵌套深度限制；3 层之内能覆盖
  proposer→critic→judge 的 debate 场景，再深的递归直接拒绝
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from loguru import logger

from chameleon.core.api.exceptions import (
    AgentNotFoundError,
    BusinessError,
    ResultCode,
)
from chameleon.core.observe.context import (
    ObservationType,
    current_observation_id,
    observe,
)
from chameleon.providers.base import (
    AGENTS,
    PROVIDERS,
    InvokeContext,
    InvokeResult,
    Message,
)

#: 跨 agent 调用嵌套深度上限（防递归爆栈）
MAX_DEPTH = 3


@dataclass
class A2ACallSpec:
    """A2A 调用入参

    Attributes:
        source_agent_key: 发起方 agent key（仅作 trace 标记 / 审计；不查注册表）
        target_agent_key: 目标 agent key（必须在 AGENTS 注册表）
        input: 透传给 target 的输入（str 或 Message 列表）
        trace_id: 根 trace id（写到 InvokeContext.request_id；用于嵌套 observe parent_id）
        budget_remaining: 剩余 token 预算；0 或负值拒绝调用
        depth: 当前 A2A 嵌套深度（caller 应在每层 +1 传下去）
        session_id: 可选；不传时按 "a2a-{trace_id}" 兜底（A2A 通常无持久 session）
        app_id: 可选；用于审计 / 配额；不传按 "a2a" 兜底
        context_vars: 透传给 InvokeContext.context_vars
        options: 透传给 InvokeContext.options
    """

    source_agent_key: str
    target_agent_key: str
    input: str | list[Message]
    trace_id: str
    budget_remaining: int
    depth: int = 0
    session_id: str | None = None
    app_id: str | None = None
    context_vars: dict[str, Any] | None = None
    options: dict[str, Any] | None = None


@dataclass
class A2AResult:
    """A2A 调用结果

    Attributes:
        result: 目标 agent 的 InvokeResult
        budget_remaining: 调用后剩余 token 预算（max(0, before - consumed)）
        budget_consumed: 本次调用消耗的 token（取 usage.total_tokens；缺则 0）
        duration_ms: 端到端耗时
        sub_observation_id: 本次 A2A 调用建立的 observation id（接入 trace tree）
    """

    result: InvokeResult
    budget_remaining: int
    budget_consumed: int
    duration_ms: int
    sub_observation_id: str


class AgentRunner:
    """A2A 协议执行器

    用法：
        result = await AgentRunner.call_agent(A2ACallSpec(
            source_agent_key="proposer",
            target_agent_key="critic",
            input="some argument",
            trace_id=ctx.request_id,
            budget_remaining=10_000,
            depth=1,
        ))
    """

    @classmethod
    async def call_agent(cls, spec: A2ACallSpec) -> A2AResult:
        cls._assert_red_lines(spec)

        agent_def = AGENTS.get(spec.target_agent_key)
        if agent_def is None:
            raise AgentNotFoundError(
                message=f"A2A target agent 不存在: {spec.target_agent_key}"
            )
        provider = PROVIDERS.get(agent_def.provider)
        if provider is None:
            raise BusinessError(
                ResultCode.RegistryError,
                message=f"A2A provider 未注册: {agent_def.provider}",
            )

        t0 = time.perf_counter()
        async with observe(
            observation_type=ObservationType.AGENT,
            name=f"a2a:{spec.source_agent_key}->{spec.target_agent_key}",
            parent_id=current_observation_id(),
            meta={
                "source": spec.source_agent_key,
                "target": spec.target_agent_key,
                "depth": spec.depth,
                "budget_before": spec.budget_remaining,
            },
        ) as obs:
            ctx = InvokeContext(
                agent_def=agent_def,
                input=spec.input,
                history=[],  # A2A 短链，不带历史；如需历史由 caller 在 input 拼好
                session_id=spec.session_id or f"a2a-{spec.trace_id[:16]}",
                provider_conv_id=None,
                context_vars={
                    **(spec.context_vars or {}),
                    "_a2a_source": spec.source_agent_key,
                    "_a2a_depth": spec.depth,
                    "_a2a_trace": spec.trace_id,
                },
                options=spec.options or {},
                app_id=spec.app_id or "a2a",
                stream=False,
                request_id=spec.trace_id,
            )
            try:
                result = await provider.invoke(ctx)
            except Exception as e:
                logger.exception(
                    "a2a invoke failed | {} -> {} | err={}",
                    spec.source_agent_key,
                    spec.target_agent_key,
                    e,
                )
                obs.meta["status"] = "failed"
                obs.meta["error"] = type(e).__name__
                raise

            consumed = (
                result.usage.total_tokens
                if result.usage and result.usage.total_tokens
                else 0
            )
            updated_budget = max(0, spec.budget_remaining - consumed)
            obs.meta["budget_after"] = updated_budget
            obs.meta["tokens_consumed"] = consumed
            sub_obs_id = obs.request_id

        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "a2a call ok | {} -> {} | depth={} | budget={}->{} | dur={}ms",
            spec.source_agent_key,
            spec.target_agent_key,
            spec.depth,
            spec.budget_remaining,
            updated_budget,
            duration_ms,
        )
        return A2AResult(
            result=result,
            budget_remaining=updated_budget,
            budget_consumed=consumed,
            duration_ms=duration_ms,
            sub_observation_id=sub_obs_id,
        )

    @staticmethod
    def _assert_red_lines(spec: A2ACallSpec) -> None:
        if not spec.trace_id or not isinstance(spec.trace_id, str):
            raise BusinessError(
                ResultCode.ValidationError,
                message="A2A 调用必须传 trace_id（observation tree 不可断链）",
            )
        if spec.budget_remaining <= 0:
            raise BusinessError(
                ResultCode.ValidationError,
                message=(
                    f"A2A budget 已耗尽: remaining={spec.budget_remaining}; "
                    "防 agents 互调爆 token"
                ),
            )
        if spec.depth >= MAX_DEPTH:
            raise BusinessError(
                ResultCode.ValidationError,
                message=(
                    f"A2A 嵌套深度达上限 {MAX_DEPTH}（防递归爆栈）；"
                    f"当前 depth={spec.depth}"
                ),
            )
        if not spec.target_agent_key:
            raise BusinessError(
                ResultCode.ValidationError, message="A2A target_agent_key 必填"
            )
        if not spec.source_agent_key:
            raise BusinessError(
                ResultCode.ValidationError, message="A2A source_agent_key 必填"
            )


async def call_agent(
    *,
    source: str,
    target: str,
    input: str | list[Message],
    trace_id: str,
    budget_remaining: int,
    depth: int = 0,
    session_id: str | None = None,
    app_id: str | None = None,
    context_vars: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
) -> A2AResult:
    """便捷 helper —— 等价 AgentRunner.call_agent(A2ACallSpec(...))"""
    return await AgentRunner.call_agent(
        A2ACallSpec(
            source_agent_key=source,
            target_agent_key=target,
            input=input,
            trace_id=trace_id,
            budget_remaining=budget_remaining,
            depth=depth,
            session_id=session_id,
            app_id=app_id,
            context_vars=context_vars,
            options=options,
        )
    )
