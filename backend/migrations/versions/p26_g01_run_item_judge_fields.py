"""模块 G：dataset_run_items 加 score_reason / field_scores / reference_output

为 AI 评分理由、DSL 逐字段评分、GSB 参照回答铺字段（一次到位，nullable 不影响存量）。

Revision ID: p26_g01_run_item_judge_fields
Revises: p26_d01_drop_graph_node_runs
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "p26_g01_run_item_judge_fields"
down_revision: Union[str, Sequence[str], None] = "p26_d01_drop_graph_node_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dataset_run_items",
        sa.Column("score_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "dataset_run_items",
        sa.Column("field_scores", sa.JSON(), nullable=True),
    )
    op.add_column(
        "dataset_run_items",
        sa.Column("reference_output", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dataset_run_items", "reference_output")
    op.drop_column("dataset_run_items", "field_scores")
    op.drop_column("dataset_run_items", "score_reason")
