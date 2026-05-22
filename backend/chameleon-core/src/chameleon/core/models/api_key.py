"""ApiKey + CallLog 模型

v0.2 重构：
- ApiKey.app_id String 删除 unique 约束（一 app 多 key），加 FK 引用 apps.app_key
- ApiKey.created_by_id 重命名为 created_by_user_id + 加 FK 引用 users.id
- CallLog.app_id / agent_key 加 FK；加 api_key_id FK + error_class 字段
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, TimestampMixin
from chameleon.core.utils.snowflake import next_id


class ApiKey(Base, TimestampMixin):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    # app_id 是字符串 slug（对外可读，业务方调用时不直接出现，但所有表统一）
    # FK 引用 apps.app_key（CASCADE：删 app 时 key 一起删）
    app_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("apps.app_key", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_api_keys_app", "app_id"),
        Index("ix_api_keys_revoked", "revoked_at"),
        Index("ix_api_keys_created_by", "created_by_user_id"),
    )


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    app_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("apps.app_key", ondelete="CASCADE"),
        nullable=False,
    )
    # agent_key FK 推到 P5（agents 表由 registry sync 在 P5 填充）
    agent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    api_key_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stream: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    code: Mapped[int] = mapped_column(Integer, nullable=False)
    error_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # P16-E2 trace: spans [{name, start_ms, end_ms, status, error?, meta?}]
    spans: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 入参快照（input + options + history 摘要等）
    request_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 出参快照（answer + steps + citations + tool_calls + usage）
    response_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_call_logs_created_at", "created_at"),
        Index("ix_call_logs_app_created", "app_id", "created_at"),
        Index("ix_call_logs_agent_created", "agent_key", "created_at"),
        Index("ix_call_logs_success_created", "success", "created_at"),
        Index("ix_call_logs_api_key", "api_key_id"),
    )
