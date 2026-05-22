"""P18.1: GraphEngine 持久层 —— graphs / graph_runs / graph_node_runs

业务：Dify 风可视化工作流；图声明落 graphs.spec JSONB，每次跑生成一条 graph_run + N 条 node_run。
graph_node_runs.request_id 与 call_logs.parent_id 串联，trace tree drawer 直接复用。

Revision ID: p18_w9_graphs
Revises: p17_w7_scores
Create Date: 2026-05-23 17:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p18_w9_graphs"
down_revision: Union[str, Sequence[str], None] = "p17_w7_scores"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "graphs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("graph_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "schema_version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("graph_key", name="uq_graphs_key"),
    )

    op.create_table(
        "graph_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "graph_id",
            sa.BigInteger(),
            sa.ForeignKey("graphs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("node_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("request_id", name="uq_graph_runs_rid"),
    )
    op.create_index(
        "ix_graph_runs_graph", "graph_runs", ["graph_id", "created_at"]
    )

    op.create_table(
        "graph_node_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "graph_run_id",
            sa.BigInteger(),
            sa.ForeignKey("graph_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("node_type", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("input", sa.JSON(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_graph_node_runs_run", "graph_node_runs", ["graph_run_id"]
    )
    op.create_index(
        "ix_graph_node_runs_rid", "graph_node_runs", ["request_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_graph_node_runs_rid", table_name="graph_node_runs")
    op.drop_index("ix_graph_node_runs_run", table_name="graph_node_runs")
    op.drop_table("graph_node_runs")
    op.drop_index("ix_graph_runs_graph", table_name="graph_runs")
    op.drop_table("graph_runs")
    op.drop_table("graphs")
