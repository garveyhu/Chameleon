"""ChatSession + Message 模型

S1/S2 会话与可观测重构：原 `conversations` 表整删，重设为 `sessions` 表，加
- `api_key_id`：发起会话的 owner key（嵌入式/openai/API 凡是经 key 鉴权的都落进来，
  便于按 key 统计/限流；admin/playground/eval 等无 key 路径为 NULL）
- `end_user_id`：使用 app 的终端用户外部标识（接入方提供的不透明字符串）。
  这是会话管理一切产品功能（历史侧栏 / 跨设备同步 / 按用户计费）的前提。

类名 `ChatSession`，避开与 SQLAlchemy `Session` 的歧义；表名直接 `sessions`，
名实相符（事实主键就是 session_id）。Message 表沿用，加冗余 end_user_id。
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


class ChatSession(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # agent_key FK 推到 P5（agents 表由 registry sync 在 P5 填充）
    agent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # app_id：调用方/来源自由标签（同 ApiKey.app_id 语义）
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # owner key（嵌入/API 入口处盖章；admin/playground 为 NULL）
    api_key_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 终端用户外部 id（接入方传入；匿名设备模式则为 hash(device_id)）
    end_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_conv_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_sessions_agent_key", "agent_key"),
        Index("ix_sessions_app_id", "app_id"),
        Index("ix_sessions_end_user_id", "end_user_id"),
        Index("ix_sessions_api_key_id", "api_key_id"),
        Index("ix_sessions_last_message_at", "last_message_at"),
        Index(
            "ix_sessions_app_user_last_msg",
            "app_id",
            "end_user_id",
            "last_message_at",
        ),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # 老 plain text 字段；P19.4 起多模态消息可同时（或仅）写 content_blocks
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # P19.4 PR #40：ContentBlock 列表（text / image_url / audio_url）
    # NULL = 纯文本消息（向后兼容）；非 NULL = 优先取这个还原 ProviderMessage
    content_blocks: Mapped[list | None] = mapped_column(JSON, nullable=True)
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
    # S2 重构：冗余 end_user_id（避免按用户分析时回去 join sessions）
    end_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 本条消息所属调用的 trace_id（= request_id），用于反馈按钮关联 score 表
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_messages_session_seq", "session_id", "seq", unique=True),
        Index("ix_messages_parent", "parent_message_id"),
        Index("ix_messages_end_user_id", "end_user_id"),
        Index("ix_messages_request_id", "request_id"),
    )
