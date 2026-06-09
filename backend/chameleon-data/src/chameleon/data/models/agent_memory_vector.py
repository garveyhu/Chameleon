"""agentkit 语义记忆向量表 —— ctx.memory.search 的 hybrid 召回底座。

与 [[agent_memory]]（KV 真相源）旁路并存：ctx.memory.set 时把值的文本投影 embed 入本表，
ctx.memory.search 按 (agent_key, scope_ref) 隔离做 vector + BM25 hybrid 召回。
text_search 存 jieba 切词（中文 BM25），content_tsv（GENERATED tsvector）+ GIN 见迁移。
按 (agent_key, scope_ref, mkey) 唯一，与 agent_memory 同维度（scope 隔离同纪律）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.data.models.base import Base

# pgvector.sqlalchemy.Vector —— 与 chunks 同一 1536 空间（inventory.embedding_dim 对齐）
try:
    from pgvector.sqlalchemy import Vector
except ImportError as e:
    raise ImportError("pgvector package required: pip install pgvector") from e

_EMBED_DIM = 1536  # 与 inventory.embedding_dim() 默认一致；改维度需新 migration


class AgentMemoryVector(Base):
    __tablename__ = "agent_memory_vector"
    __table_args__ = (
        UniqueConstraint(
            "agent_key", "scope_ref", "mkey", name="uq_agent_memory_vector_key"
        ),
        Index("ix_agent_memory_vector_scope", "agent_key", "scope_ref"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_key: Mapped[str] = mapped_column(String(128), nullable=False)
    #: 作用域引用：end_user_id（跨会话）或 session_id（退化）——同 agent_memory
    scope_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    mkey: Mapped[str] = mapped_column(String(128), nullable=False)
    #: 值的文本投影（embed 输入 + 召回回显；str 原样 / 其它 json.dumps）
    text: Mapped[str] = mapped_column(Text, nullable=False)
    #: jieba 切词文本（中文 BM25）；content_tsv（GENERATED）优先此列、回退 text（见迁移）
    text_search: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(_EMBED_DIM), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
