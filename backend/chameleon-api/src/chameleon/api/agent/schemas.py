"""agent 模块 DTO"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from chameleon.providers.base.types import (
    Citation,
    StepRecord,
    ToolCallRecord,
    Usage,
)

# ── Invoke 入参 ─────────────────────────────────────────


class MessageInput(BaseModel):
    """client 自管历史时一条消息"""

    role: Literal["user", "assistant", "system", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = None


class InvokeRequest(BaseModel):
    input: str | list[MessageInput] = Field(
        ..., description="str → 取 session 历史；list → 客户端自管历史"
    )
    session_id: str | None = Field(None, description="缺省 → 新建会话，响应回显新 ID")
    user: str | None = Field(
        None,
        description="终端用户外部标识（接入方维护的不透明字符串，类似 Dify/OpenAI 协议的 user）。"
        "用于会话归属、历史隔离、按用户统计计费。",
    )
    stream: bool = Field(False, description="true → SSE；false → 单次 JSON")
    context: dict[str, Any] = Field(
        default_factory=dict, description="业务上下文（user_id 等）"
    )
    options: dict[str, Any] = Field(
        default_factory=dict, description="provider-specific 运行时覆盖"
    )

    model_config = ConfigDict(extra="forbid")


# ── Invoke 响应 ─────────────────────────────────────────


class InvokeResponse(BaseModel):
    session_id: str
    request_id: str
    answer: str
    steps: list[StepRecord]
    citations: list[Citation]
    tool_calls: list[ToolCallRecord]
    usage: Usage | None


# ── Agent 元信息 ────────────────────────────────────────


class AgentItem(BaseModel):
    key: str
    provider: str
    description: str
    version: str | None
    tags: list[str]
