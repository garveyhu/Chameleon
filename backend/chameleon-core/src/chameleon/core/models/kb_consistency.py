"""KbConsistencyReport ORM —— P21.3 PR #65

业务：扫描 KB 中的 chunks 一致性问题（orphan / dim_mismatch / zero_vector），
落 quarantine 标记 + 报告；不在线物理删（红线 plan §2 P21）。

scan → 标 chunks.quarantined=True + reason；写 kb_consistency_reports 行
repair → admin 显式确认后物理删 quarantined chunks；update report status
"""

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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, snowflake_pk


class KbConsistencyReport(Base):
    """一次 KB 一致性扫描的报告（含 issues 列表）"""

    __tablename__ = "kb_consistency_reports"

    id: Mapped[int] = snowflake_pk()
    kb_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    # status：pending / running / done / fixed / failed
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    # issues: [{ type: 'orphan_chunk'|'dim_mismatch'|'zero_vector',
    #            chunk_id: int, kb_id: int, reason: str }]
    issues: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 扫描统计
    scanned_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    quarantined_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    # repair 后实际删的数量
    fixed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    error_message: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_kb_consistency_kb_started", "kb_id", "started_at"),
    )
