"""Graph ORM —— P18.1 工作流引擎持久层

三张表：
- graphs        图声明（spec 落 JSONB）
- graph_runs    一次执行的总记录
- graph_node_runs 每节点执行的子记录，request_id 与 call_logs 串联
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, SoftDeleteMixin, TimestampMixin, snowflake_pk
from chameleon.core.models.workspace import WorkspaceScopedMixin


class Graph(Base, TimestampMixin, SoftDeleteMixin, WorkspaceScopedMixin):
    """工作流图声明"""

    __tablename__ = "graphs"

    id: Mapped[int] = snowflake_pk()
    graph_key: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    # GraphSpec.model_dump() 落 JSONB（draft 版本，可改）
    spec: Mapped[dict] = mapped_column(JSON, nullable=False)
    # P22.3：published 版本快照（freeze；admin publish 时从 spec 拷贝过来）
    published_spec: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    published_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )


class GraphRun(Base):
    """一次完整执行的记录"""

    __tablename__ = "graph_runs"

    id: Mapped[int] = snowflake_pk()
    graph_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("graphs.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 与 call_logs.request_id 一致，串联 trace tree
    request_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )  # pending/running/success/failed/cancelled
    input: Mapped[dict] = mapped_column(JSON, nullable=False)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    node_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("ix_graph_runs_graph", "graph_id", "created_at"),)


class GraphNodeRun(Base):
    """单节点执行记录"""

    __tablename__ = "graph_node_runs"

    id: Mapped[int] = snowflake_pk()
    graph_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("graph_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 写入 call_logs.parent_id 实现 trace 串联（PR #21 起填充）
    request_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_graph_node_runs_run", "graph_run_id"),
        Index("ix_graph_node_runs_rid", "request_id"),
    )
