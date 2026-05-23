"""Conversation + Message 模型

v0.2 重构：
- agent_key 加 FK 引用 agents.agent_key
- app_id 加 FK 引用 apps.app_key
- provider 字段废除（agents 表已有 source 字段提供同等信息）
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, SoftDeleteMixin, TimestampMixin
from chameleon.core.utils.snowflake import next_id


class Conversation(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # agent_key FK 推到 P5（agents 表由 registry sync 在 P5 填充）
    agent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    app_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("apps.app_key", ondelete="CASCADE"),
        nullable=False,
    )
    provider_conv_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_conversations_app_last_msg", "app_id", "last_message_at"),
        Index("ix_conversations_agent_last_msg", "agent_key", "last_message_at"),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    steps: Mapped[list | None] = mapped_column(JSON, nullable=True)
    citations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # P18.5 PR #27：消息分支 —— 指向同 session 的"前一条" message（fork 起点）
    # NULL = 线性主线；非 NULL = 该消息从该 parent 分叉而来
    parent_message_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_messages_session_seq", "session_id", "seq", unique=True),
        Index("ix_messages_parent", "parent_message_id"),
    )
