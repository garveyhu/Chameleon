"""Agent ↔ KB 多对多关联表（P16-C）"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.data.models.base import Base


class AgentKbLink(Base):
    """Agent 挂载 KB 的关联表。
    复合主键 (agent_id, kb_id) 保证幂等；删 agent / kb 级联清。
    """

    __tablename__ = "agent_kb_link"

    agent_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    kb_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("ix_agent_kb_link_kb", "kb_id"),)
