"""drop graph_node_runs —— 节点明细收口到 call_logs span 行

可观测溯源 LangSmith 化重构（docs/plans/2026-05-29-observability-langsmith-refactor.md）：
graph 节点执行明细统一落 call_logs（observation_type='span' + parent_id 自引树，
LLM 调用作为嵌套 generation），call_logs 成为唯一 trace 真相源。graph_node_runs
（旧的并行节点明细表）下线。

graph_runs 保留 —— 它是运行头 + human-input 暂停/恢复的可恢复状态锚
（HumanInputPending.graph_run_id FK），不是观测，call_logs 替代不了。

Revision ID: p26_d01_drop_graph_node_runs
Revises: p26_c01_agent_default_model_code
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p26_d01_drop_graph_node_runs"
down_revision = "p26_c01_agent_default_model_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_graph_node_runs_rid", table_name="graph_node_runs")
    op.drop_index("ix_graph_node_runs_run", table_name="graph_node_runs")
    op.drop_table("graph_node_runs")


def downgrade() -> None:
    op.create_table(
        "graph_node_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("graph_run_id", sa.BigInteger(), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("node_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["graph_run_id"], ["graph_runs.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_graph_node_runs_run", "graph_node_runs", ["graph_run_id"]
    )
    op.create_index(
        "ix_graph_node_runs_rid", "graph_node_runs", ["request_id"]
    )
