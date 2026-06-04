"""模块 G：dataset_items 加 reference_output + eval_jobs 加 judge_config

为 GSB 参照回答（区别 expected_output 金标准语义）与 judge 多模式参数
（criteria / dsl 文本 / gsb 参照源开关）铺字段；nullable，不影响存量。

down_revision 挂 p27_a01_model_upstream_fields，保持线性单 head（不碰 newapi 字段）。

Revision ID: p27_g02_ref_judge_config
Revises: p27_a01_model_upstream_fields
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "p27_g02_ref_judge_config"
down_revision: Union[str, Sequence[str], None] = "p27_a01_model_upstream_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dataset_items",
        sa.Column("reference_output", sa.JSON(), nullable=True),
    )
    op.add_column(
        "eval_jobs",
        sa.Column("judge_config", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("eval_jobs", "judge_config")
    op.drop_column("dataset_items", "reference_output")
