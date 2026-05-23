"""P21.2 PR #64: dataset_run_items 加 eval_scores JSONB

业务：跑完 dataset_run 后自动按 EvalTemplate 跑评分；多 metric 分数写一行。

Revision ID: p21_w37_eval_scores
Revises: p21_w35_eval_templates
Create Date: 2027-01-31 12:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p21_w37_eval_scores"
down_revision: Union[str, Sequence[str], None] = "p21_w35_eval_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dataset_run_items",
        sa.Column("eval_scores", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dataset_run_items", "eval_scores")
