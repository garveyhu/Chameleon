"""KnowledgeBase + Document + Chunk（pgvector）"""

from sqlalchemy import (
    JSON,
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, SoftDeleteMixin, TimestampMixin
from chameleon.core.models.workspace import WorkspaceScopedMixin
from chameleon.core.utils.snowflake import next_id

# pgvector.sqlalchemy.Vector —— v1 全局维度 1536（与 inventory.embedding_dim 对齐）
try:
    from pgvector.sqlalchemy import Vector
except ImportError as e:
    raise ImportError("pgvector package required: pip install pgvector") from e

_EMBED_DIM = 1536  # 与 inventory.embedding_dim() 默认一致；改维度需新 migration


class KnowledgeBase(Base, TimestampMixin, SoftDeleteMixin, WorkspaceScopedMixin):
    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    kb_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_dim: Mapped[int] = mapped_column(
        Integer, nullable=False, default=_EMBED_DIM
    )
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=800)
    chunk_overlap: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    # P16-C: 分块策略 / 召回参数（KB 级默认；document.chunk_strategy 覆盖）
    chunk_strategy: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: {"mode": "fixed", "chunk_size": 800, "overlap": 100},
    )
    default_top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    recall_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="vector"
    )
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Document(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    kb_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # null = 用 KB 的 chunk_strategy；非 null 覆盖
    chunk_strategy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (Index("ix_documents_kb_status", "kb_id", "status"),)


class Chunk(Base, TimestampMixin):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    doc_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 冗余，加快过滤
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(_EMBED_DIM), nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # P20.3：归属 collection（NULL = generic 默认 collection 兼容老 chunk）
    collection_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("kb_collections.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 一个原文可生成多个不同 index（同 doc + chunk 不同 'view'）—— chunk/qa/summary
    index_name: Mapped[str] = mapped_column(
        String(32), nullable=False, default="chunk"
    )
    # FAQ collection：每 chunk 内嵌问句；retrieve 时按 qa_question 走 BM25
    qa_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    # API collection：endpoint 标识（"GET /v1/users"）
    api_endpoint: Mapped[str | None] = mapped_column(String(256), nullable=True)

    __table_args__ = (
        Index("ix_chunks_kb", "kb_id"),
        Index("ix_chunks_doc_seq", "doc_id", "seq"),
        Index("ix_chunks_collection_index", "collection_id", "index_name"),
        # HNSW 向量索引在 migration 里手写（SQLAlchemy 不直接支持 HNSW 参数）
    )
