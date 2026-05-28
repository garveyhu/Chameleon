"""会话级附件 ORM（Phase B）

记录任意 session 上传过的附件：image/audio 直接进多模态 LLM；document/data 走临时 KB。
document_id / ephemeral_kb_id 是软链 —— SET NULL 而非 CASCADE，便于看到孤儿记录。

业务约束（不靠 DB FK 表达）：
- 同一 session 的所有 document 类型 SessionFile 共享一个 ephemeral_kb（session 第一次
  传文档时创建）
- session 软删时业务层级联软删 SessionFile + 关联 ephemeral_kb
- MinIO object 由后台清理任务异步删（不阻塞 HTTP 路径）
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, SoftDeleteMixin, TimestampMixin
from chameleon.core.utils.snowflake import next_id


class SessionFile(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "session_files"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    end_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    object_url: Mapped[str] = mapped_column(Text, nullable=False)
    object_id: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime: Mapped[str] = mapped_column(String(128), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # image / audio / document / data / other（widget 端 classifyKind 决定）
    kind: Mapped[str] = mapped_column(String(24), nullable=False)

    document_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    ephemeral_kb_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="uploaded", server_default="uploaded"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_session_files_session", "session_id"),
        Index("ix_session_files_end_user", "end_user_id"),
        Index("ix_session_files_kind", "kind"),
        Index("ix_session_files_status", "status"),
        Index("ix_session_files_created", "created_at"),
    )
