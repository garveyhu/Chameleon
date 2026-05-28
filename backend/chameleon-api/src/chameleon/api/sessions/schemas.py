"""conversation 模块 DTO"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChatSessionItem(BaseModel):
    id: int
    session_id: str
    agent_key: str
    app_id: str
    # S3 重构：终端用户外部 id（接入方传入；用于按用户筛 / 计费）
    end_user_id: str | None = None
    # 该 session 绑的 owner key（API/embed/openai 入口处盖章；admin 为 NULL）
    api_key_id: int | None = None
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
    # P19.4 PR #40：多模态 ContentBlock 列表（NULL = 纯文本，content 字段权威）
    content_blocks: list[dict[str, Any]] | None = None
    steps: list[dict[str, Any]] | None
    citations: list[dict[str, Any]] | None
    tool_calls: list[dict[str, Any]] | None
    usage: dict[str, Any] | None
    provider: str | None
    # P18.5 PR #27：分支起点（regenerate/edit-and-resend fork 时填）
    parent_message_id: int | None = None
    # 本条消息所属调用的 trace_id（= request_id），widget 反馈按钮按此落 score 表
    request_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppendMessageDraft(BaseModel):
    """内部用：service 层 append_message 参数（非 HTTP 入参）"""

    role: str = Field(..., pattern=r"^(user|assistant|system|tool)$")
    content: str
    # P19.4 PR #40：多模态消息可同时（或仅）传 content_blocks；service 层会
    # 把 blocks 写库，并把 flattened text 同步写 content 兼容老消费者
    content_blocks: list[dict[str, Any]] | None = None
    steps: list[dict[str, Any]] | None = None
    citations: list[dict[str, Any]] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    usage: dict[str, Any] | None = None
    provider: str | None = None
    parent_message_id: int | None = None
    # S3 重构：消息冗余 end_user_id（避免按用户分析时回去 join sessions 表）
    end_user_id: str | None = None
    # 本条消息所属调用的 trace_id（= request_id）；assistant 消息必填，user 可填
    request_id: str | None = None
