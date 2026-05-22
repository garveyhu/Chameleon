"""P17.C2: scores 表 —— call_log 评分/反馈事件

业务：widget 点赞 / LLM-as-judge / 人工标注 —— 全部以 (name, value) 形式
挂在 call_log（trace 根或子 observation）上。

写多读少，append-only，不带 updated_at。

Revision ID: p17_w7_scores
Revises: p17_w6_channels_cascade
Create Date: 2026-05-23 14:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p17_w7_scores"
down_revision: Union[str, Sequence[str], None] = "p17_w6_channels_cascade"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scores",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("call_log_id", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("string_value", sa.Text(), nullable=True),
        sa.Column("data_type", sa.String(length=16), nullable=False),
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default="api",
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_scores_call", "scores", ["call_log_id"])
    op.create_index("ix_scores_trace_name", "scores", ["trace_id", "name"])


def downgrade() -> None:
    op.drop_index("ix_scores_trace_name", table_name="scores")
    op.drop_index("ix_scores_call", table_name="scores")
    op.drop_table("scores")
