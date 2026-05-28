"""会话级附件 ORM（Phase B v2，已与 KB 解耦）

记录任意 session 上传过的附件。**临时附件不再创建 ephemeral KB**（知识库是用户手动维护
的资产，不该被会话临时文件污染）。

按解析后文本大小路由：
- 小文件（text_size ≤ 阈值）：parsed_text 存全文，use_full_text=true；service 拼全文进 system prompt
- 大文件（> 阈值）：use_full_text=false，切块到 session_file_chunks（带向量），按 query 检索 top-k

ephemeral_kb_id / document_id 列保留只是历史包袱，service 不再读写。
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
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

    # 解析路由（v2）：小文件全文，大文件切块
    parsed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    use_full_text: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # 历史兼容列（v1 ephemeral KB 路径用，v2 起不再写新值）
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
