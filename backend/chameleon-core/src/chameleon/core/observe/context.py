"""Observation contextvar + 嵌套上下文管理器

S4 重构：双 ContextVar 结构

1. `_CURRENT_TRACE` —— 请求级 `TraceContext`，由入口（agent.invoke / embed /
   openai / agentkit transport / KB ingest）开 scope 时一次性写入。携带：
   request_id / app_id / api_key_id / channel / agent_key / session_id /
   end_user_id —— 用于 generation 回调写 call_logs 时的归属冗余。

2. `_CURRENT_OBS_ID` —— 嵌套观测的 parent_id 链（沿用原行为）。`observe(...)`
   每次进入一个嵌套段时把当前 id 入栈，退出复位；observe 自动从 contextvar
   读 parent 完成嵌套。

设计要点：
- TraceContext 在请求生命周期内**不变**；ObservationContext 是 per-span 的，
  会嵌套。LangChain BaseLLM 回调（GenerationRecorder）触发时同时读两个：
  parent_id 从 _CURRENT_OBS_ID 拿，归属字段从 TraceContext 拿。
- 凡是没开 trace scope 的路径（如 KB 摄入裸调 resolve_llm），TraceContext
  为 None；GenerationRecorder 兜底落 `channel='internal'` 独立行。
- 与之前的 SpanRecorder（utils/spans.py）配套使用：SpanRecorder 用于在请求
  内累计 timing 打点（dump 到 root call_log.spans JSON）；TraceContext 用于
  跨 call_log 行（root + generation 子行）的归属冗余字段。S7/S8 会把
  SpanRecorder 也下沉到 ContextVar。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ObservationType(StrEnum):
    """Observation 类型枚举（与 DB 字段 observation_type 字符串对齐）

    沿用 LangFuse 命名：
    - trace      —— 顶层 trace 根（agent invoke 的最外层）
    - span       —— 通用嵌套段（不是 LLM 调用、不是工具）
    - generation —— LLM 生成调用（model / token 用量记录）
    - agent      —— Agent 推理一轮
    - tool       —— 工具调用
    - retriever  —— RAG 检索
    - evaluator  —— 自动评估
    - embedding  —— 向量化调用
    - guardrail  —— 内容审核
    """

    TRACE = "trace"
    SPAN = "span"
    GENERATION = "generation"
    AGENT = "agent"
    TOOL = "tool"
    RETRIEVER = "retriever"
    EVALUATOR = "evaluator"
    EMBEDDING = "embedding"
    GUARDRAIL = "guardrail"


# ── TraceContext：请求级归属上下文 ────────────────────────────


@dataclass(frozen=True)
class TraceContext:
    """请求级归属上下文（一次请求只 set 一次，整段生命周期内不变）

    入口处用 `open_trace_scope(...)` 写入；嵌套子观测从同一个 ContextVar 读
    （ContextVar 在 asyncio 任务间会自动 copy-on-write 传播）。
    """

    request_id: str
    channel: str = "api"  # api / openai / embed / playground / internal
    app_id: str | None = None
    api_key_id: int | None = None
    agent_key: str | None = None
    session_id: str | None = None
    end_user_id: str | None = None
    user_id: int | None = None  # 后台操作者（admin / playground），与 end_user_id 区分
    meta: dict[str, Any] = field(default_factory=dict)


_CURRENT_TRACE: ContextVar[TraceContext | None] = ContextVar(
    "current_trace_context", default=None
)


def current_trace_context() -> TraceContext | None:
    """读取当前请求级 TraceContext（无 scope 时返 None，调用方应有兜底）"""
    return _CURRENT_TRACE.get()


@asynccontextmanager
async def open_trace_scope(ctx: TraceContext):
    """请求入口处开 trace scope；退出复位

    用法（agent.service / embed / openai / ...）：
        async with open_trace_scope(TraceContext(request_id=..., ...)):
            ... 业务逻辑 ...
            # 此期间任何 BaseLLM.ainvoke() 触发的 on_llm_end 都能读到 ctx
    """
    token: Token = _CURRENT_TRACE.set(ctx)
    try:
        yield ctx
    finally:
        _CURRENT_TRACE.reset(token)


def set_trace_context(ctx: TraceContext) -> Token:
    """非缩进式 set；与 reset_trace_context 配对用 try/finally 控制生命周期。

    用于不愿因 `async with` 改一大段缩进的入口（如 agent.invoke）：

        token = set_trace_context(TraceContext(...))
        try:
            ... 大段业务逻辑保持原缩进 ...
        finally:
            reset_trace_context(token)
    """
    return _CURRENT_TRACE.set(ctx)


def reset_trace_context(token: Token) -> None:
    _CURRENT_TRACE.reset(token)


# ── ObservationContext：嵌套观测段 ───────────────────────────


_CURRENT_OBS_ID: ContextVar[str | None] = ContextVar(
    "current_observation_id", default=None
)


def current_observation_id() -> str | None:
    """读取当前激活的 observation id（即嵌套链最深一层的 request_id/span_id）"""
    return _CURRENT_OBS_ID.get()


class ObservationContext(BaseModel):
    """嵌套观测的运行时上下文

    业务侧 `async with observe(...) as o:` 拿到的对象。
    退出时自动把 ctx 数据透传给上层 callback（如 record_call）。
    """

    request_id: str
    parent_id: str | None = None
    observation_type: str = Field(default=ObservationType.GENERATION.value)
    name: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


@asynccontextmanager
async def observe(
    *,
    observation_type: str | ObservationType = ObservationType.GENERATION,
    name: str | None = None,
    request_id: str | None = None,
    parent_id: str | None = None,
    meta: dict[str, Any] | None = None,
):
    """开启一个嵌套 observation

    Args:
        observation_type: 类型枚举字符串
        name: 可读名称（如 "embedding-text-embedding-v2"）
        request_id: 显式 id；不传则生成 uuid hex
        parent_id: 显式父；不传时自动取 contextvar 当前值
        meta: 业务自定义元数据

    Yields:
        ObservationContext（业务侧可在 with 块内修改 meta）

    退出时恢复上一级 contextvar；不直接写 DB——record_call 由调用方按需调。
    """
    rid = request_id or uuid.uuid4().hex
    inherited_parent = parent_id if parent_id is not None else _CURRENT_OBS_ID.get()
    obs = ObservationContext(
        request_id=rid,
        parent_id=inherited_parent,
        observation_type=str(observation_type),
        name=name,
        meta=dict(meta or {}),
    )

    token: Token = _CURRENT_OBS_ID.set(rid)
    try:
        yield obs
    finally:
        _CURRENT_OBS_ID.reset(token)
