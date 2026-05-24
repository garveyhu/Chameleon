"""P23 v1.1 PR A6: 新增 human_input_pending 表（工作流人工回填断点）

[SCHEMA-CHANGE] 仅新增表，不动既有表。合并 train 中 re-parent 到 C 链尾
p23_w51_channel_keys（原 revises p22_w47_app_templates 与 C 的 p23_w49_calllog_dims
撞同一 down_revision，故重排）。

Revision ID: p23_w52_human_input_pending
Revises: p23_w51_channel_keys
Create Date: 2026-05-24 12:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p23_w52_human_input_pending"
down_revision: Union[str, Sequence[str], None] = "p23_w51_channel_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "human_input_pending",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("graph_run_id", sa.BigInteger(), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("input_schema", sa.JSON(), nullable=True),
        sa.Column("node_input", sa.JSON(), nullable=True),
        sa.Column("resume_state", sa.JSON(), nullable=True),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["graph_run_id"], ["graph_runs.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_human_input_pending_run", "human_input_pending", ["graph_run_id"]
    )
    op.create_index(
        "ix_human_input_pending_status",
        "human_input_pending",
        ["status", "timeout_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_human_input_pending_status", table_name="human_input_pending")
    op.drop_index("ix_human_input_pending_run", table_name="human_input_pending")
    op.drop_table("human_input_pending")
