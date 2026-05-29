"""KnowledgeBase + Document + Chunk（pgvector）"""

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.data.models.base import Base, SoftDeleteMixin, TimestampMixin
from chameleon.data.utils.snowflake import next_id

# pgvector.sqlalchemy.Vector —— v1 全局维度 1536（与 inventory.embedding_dim 对齐）
try:
    from pgvector.sqlalchemy import Vector
except ImportError as e:
    raise ImportError("pgvector package required: pip install pgvector") from e

_EMBED_DIM = 1536  # 与 inventory.embedding_dim() 默认一致；改维度需新 migration


class KnowledgeBase(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    kb_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 自定义图标：base64 data URL（小图；缺省走前端默认图标）
    icon: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    # 保留字段（曾用于区分会话临时 KB；v2 起临时附件不再进 KB 域，但字段保留供未来分类用）
    kind: Mapped[str] = mapped_column(
        String(24), nullable=False, default="normal", server_default="normal"
    )


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
    # P22.4：文档媒介类型（text / image / pdf；NULL 兼容老数据 = text）
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="text", server_default="text"
    )
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 文档级启停：enabled=false 时整篇文档的 chunk 不参与检索（与 chunk.enabled 叠加）
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
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
    # P21.3：一致性扫描标记（半软删 —— scan 标 True，repair 时物理删）
    quarantined: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    quarantine_reason: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    # P22.4：chunk 媒介类型（text / image；多模态检索时按 kind 过滤 / 路由）
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="text", server_default="text"
    )
    # P22.4：原始资源 URL（image 上传后填 MinIO URL；text chunk 通常为空）
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # KB-P3：段落级管理（用户启停 / 关键词 / 命中数）
    # enabled=False 的 chunk 不参与检索（与 quarantined 区分：这是用户显式停用，不会被物理删）
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    keywords: Mapped[list | None] = mapped_column(JSON, nullable=True)
    hit_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # KB-P4-2：parent-child 分层。child 块精准召回，命中时返回此 parent 大块作上下文。
    # NULL = 非分层块（按自身 content 返回）。
    parent_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 中文关键词召回：jieba 切词后的 content（空格连接），content_tsv 优先按它生成
    # （PG 'simple' 不切中文 → 直接对 content 建 tsvector 中文 BM25 无效）。
    # NULL（老块未回填）时 content_tsv 回退用原始 content。
    content_search: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_chunks_kb", "kb_id"),
        Index("ix_chunks_doc_seq", "doc_id", "seq"),
        Index("ix_chunks_collection_index", "collection_id", "index_name"),
        Index("ix_chunks_quarantined", "quarantined"),
        Index("ix_chunks_kind", "kind"),
        # HNSW 向量索引在 migration 里手写（SQLAlchemy 不直接支持 HNSW 参数）
    )
