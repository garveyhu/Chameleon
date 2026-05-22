"""Observation contextvar + 嵌套上下文管理器

设计：
- ContextVar 保存当前 "active observation id"（即 call_log.request_id）
- async with observe(...) 进入时：把传入 / 生成的 id 写入 ContextVar；
  自动从 ContextVar 取上一级当 parent_id
- 退出时恢复上一级 ContextVar（栈式语义）

这套机制让"嵌套调用"不需要业务侧到处手传 parent_id。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
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


# ── contextvar ─────────────────────────────────────────────


_CURRENT_OBS_ID: ContextVar[str | None] = ContextVar(
    "current_observation_id", default=None
)


def current_observation_id() -> str | None:
    """读取当前激活的 observation id（即 call_log.request_id）"""
    return _CURRENT_OBS_ID.get()


# ── 上下文模型 ─────────────────────────────────────────────


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


# ── 嵌套上下文管理器 ───────────────────────────────────────


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
