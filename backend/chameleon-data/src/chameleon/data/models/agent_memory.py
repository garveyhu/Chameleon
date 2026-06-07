"""agentkit 智能体记忆表 —— ctx.memory 的 kv 持久化。

按 (agent_key, scope_ref, mkey) 唯一：scope_ref 优先用 end_user_id（跨会话记忆），
无身份时退化为 session_id。仅 source='local' 的 @agent 通过 ctx.memory 读写。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.data.models.base import Base


class AgentMemory(Base):
    __tablename__ = "agent_memory"
    __table_args__ = (
        UniqueConstraint("agent_key", "scope_ref", "mkey", name="uq_agent_memory_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    #: 作用域引用：end_user_id（跨会话）或 session_id（退化）
    scope_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    mkey: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
