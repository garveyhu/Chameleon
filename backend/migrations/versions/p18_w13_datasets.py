"""P18.3: datasets + dataset_items 表

业务：从 call_log 一键采样 + 人工标注 → Eval 数据集。
红线：dataset_items 不存原始 PII，input_payload 强制脱敏（hash + length + token）。

Revision ID: p18_w13_datasets
Revises: p18_w12_tools
Create Date: 2026-05-23 19:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p18_w13_datasets"
down_revision: Union[str, Sequence[str], None] = "p18_w12_tools"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "item_count", sa.Integer(), nullable=False, server_default="0"
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
    )

    op.create_table(
        "dataset_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.BigInteger(),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_call_log_id", sa.String(length=64), nullable=True),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("expected_output", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
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
    )
    op.create_index(
        "ix_dataset_items_ds", "dataset_items", ["dataset_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_dataset_items_ds", table_name="dataset_items")
    op.drop_table("dataset_items")
    op.drop_table("datasets")
