"""dataset_runs 加 judge_config（持久化评分配置：criteria / 裁判模型等）

落库口径（与 ORM dataset.py DatasetRun 对齐）：
- judge_config（JSON, nullable）：本次运行的 judge 配置——评分要点 criteria、裁判模型
  judge_model、dsl 文本等。原先只在运行时传入、未落库，导致运行详情看不到「裁判模型 /
  评分要点」。持久化后运行详情可完整回溯本次评分配置。

全 nullable，旧数据零影响（迁移前的 run 该列 NULL，详情按缺省隐藏 judge 配置块）。
down_revision 挂 p27_x03_dataset_system_prompt，保持线性单 head。

Revision ID: p27_x04_run_judge_config
Revises: p27_x03_dataset_system_prompt
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "p27_x04_run_judge_config"
down_revision: Union[str, Sequence[str], None] = "p27_x03_dataset_system_prompt"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dataset_runs",
        sa.Column("judge_config", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dataset_runs", "judge_config")
