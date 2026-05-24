"""HumanInputPending ORM —— 工作流人工回填断点（v1.1 PR A6）

human_input 节点触发暂停时落一行：记录断点上下文（prompt/schema/node_input）+
恢复所需的已完成节点输出快照（resume_state）。人工回填 value 后 resume，
Orchestrator 以 resume_state + {node_id: value} 作 seed 恢复执行。

[SCHEMA-CHANGE] 新增表，不动既有表（与 Agent C 的 alembic 同步：本表 migration
revises p22_w47_app_templates）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, TimestampMixin, snowflake_pk


class HumanInputPending(Base, TimestampMixin):
    """工作流人工回填断点"""

    __tablename__ = "human_input_pending"

    id: Mapped[int] = snowflake_pk()
    graph_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("graph_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # pending / resolved / timeout / cancelled
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 期望输入的 JSON schema（前端渲染表单用）；避开 SQLAlchemy 保留名 schema
    input_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 节点暂停时收到的 input（给审核人上下文）
    node_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 已完成节点输出快照：{node_id: output}，resume 时作 seed 重放
    resume_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 人工回填的值（resolve 时写入）
    value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 超时时刻（APScheduler 扫到 < now 且仍 pending 的标 timeout）
    timeout_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_human_input_pending_run", "graph_run_id"),
        Index("ix_human_input_pending_status", "status", "timeout_at"),
    )
