"""P18.3 PR #25: dataset_runs + dataset_run_items 表

跑一次 dataset = 一条 dataset_run + N 条 dataset_run_items（每个 item 跑一次 invoke + 计分）。

Revision ID: p18_w13_dataset_runs
Revises: p18_w13_datasets
Create Date: 2026-05-23 19:50:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p18_w13_dataset_runs"
down_revision: Union[str, Sequence[str], None] = "p18_w13_datasets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dataset_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.BigInteger(),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("agent_key", sa.String(length=64), nullable=True),
        sa.Column("model_override", sa.String(length=64), nullable=True),
        sa.Column("prompt_override", sa.Text(), nullable=True),
        sa.Column(
            "judge",
            sa.String(length=32),
            nullable=False,
            server_default="exact_match",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_dataset_runs_ds", "dataset_runs", ["dataset_id", "created_at"]
    )

    op.create_table(
        "dataset_run_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "dataset_run_id",
            sa.BigInteger(),
            sa.ForeignKey("dataset_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dataset_item_id",
            sa.BigInteger(),
            sa.ForeignKey("dataset_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actual_output", sa.JSON(), nullable=True),
        sa.Column("score", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_dataset_run_items_run", "dataset_run_items", ["dataset_run_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_dataset_run_items_run", table_name="dataset_run_items")
    op.drop_table("dataset_run_items")
    op.drop_index("ix_dataset_runs_ds", table_name="dataset_runs")
    op.drop_table("dataset_runs")
