"""会话级附件切块 ORM（v2，独立于 KB 域）

大文件（解析后字符数超过阈值）切块时落这张表。**独立于 knowledge_bases / chunks**
—— 知识库是用户手动维护的资产，临时上传不应该污染那边的数据模型。

检索流程：
1. embedding 服务对 query 出一条向量
2. SELECT ... FROM session_file_chunks WHERE session_id=? ORDER BY embedding <=> :qvec LIMIT top_k
3. 拼成 RAG 系统消息塞 LLM history（与小文件 parsed_text 全文路径汇合）

session 软删时业务层级联软删本表行（DB 上有 FK CASCADE 兜底，但 service 走 soft delete）。
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.data.models.base import Base, SoftDeleteMixin, TimestampMixin
from chameleon.data.utils.snowflake import next_id

try:
    from pgvector.sqlalchemy import Vector
except ImportError as e:  # pragma: no cover
    raise ImportError("pgvector package required: pip install pgvector") from e

_EMBED_DIM = 1536  # 与 chameleon.data.models.knowledge._EMBED_DIM 对齐


class SessionFileChunk(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "session_file_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    session_file_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("session_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ord_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(_EMBED_DIM), nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        # 复合索引由 migration 直接 raw SQL 建（含 WHERE deleted_at IS NULL），这里只声明
        # 普通索引兜底，避免 ORM-DB drift 检测炸。
        Index("ix_sfc_file", "session_file_id"),
    )
