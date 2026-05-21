"""conversation 模块 DTO"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConversationItem(BaseModel):
    id: int
    session_id: str
    agent_key: str
    provider: str | None = None  # v0.2 字段已删；保留 schema 兼容外部调用方
    app_id: str
    provider_conv_id: str | None
    title: str | None
    meta: dict[str, Any] | None
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageItem(BaseModel):
    id: int
    session_id: str
    seq: int
    role: str
    content: str
    steps: list[dict[str, Any]] | None
    citations: list[dict[str, Any]] | None
    tool_calls: list[dict[str, Any]] | None
    usage: dict[str, Any] | None
    provider: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppendMessageDraft(BaseModel):
    """内部用：service 层 append_message 参数（非 HTTP 入参）"""

    role: str = Field(..., pattern=r"^(user|assistant|system|tool)$")
    content: str
    steps: list[dict[str, Any]] | None = None
    citations: list[dict[str, Any]] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    usage: dict[str, Any] | None = None
    provider: str | None = None
