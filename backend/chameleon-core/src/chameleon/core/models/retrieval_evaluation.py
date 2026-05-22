"""KB 检索评估批次（P16-C Bundle 4）"""

from __future__ import annotations

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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base
from chameleon.core.utils.snowflake import next_id


class RetrievalEvaluation(Base):
    """评估批次。queries 用 JSONB 存 [{query, expected_chunk_ids}]；
    results 存 {hit_at_k: {1:.., 3:.., 5:..}, mrr, latency_p50_ms, latency_p95_ms}。
    """

    __tablename__ = "retrieval_evaluation"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    kb_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    queries: Mapped[list] = mapped_column(JSON, nullable=False)
    results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recall_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_retrieval_evaluation_kb_created", "kb_id", "created_at"),
    )
