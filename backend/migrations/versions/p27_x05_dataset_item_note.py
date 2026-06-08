"""dataset_items 加 note（样本备注：描述该样本用于评测什么，非必填）

落库口径（与 ORM dataset.py DatasetItem 对齐）：
- note（Text, nullable）：样本备注，描述这条样本的评测用途 / 考察点。独立于 meta
  （meta 由采样/导入塞 source/pii 等结构化字段），note 是面向人的自由文本，在样本列表
  一等公民显示 / 编辑，并贯穿 AI 扩样 / 手动导入 / 导出。

全 nullable，旧数据零影响。down_revision 挂 p27_x04_run_judge_config，保持线性单 head。

Revision ID: p27_x05_dataset_item_note
Revises: p27_x04_run_judge_config
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "p27_x05_dataset_item_note"
down_revision: Union[str, Sequence[str], None] = "p27_x04_run_judge_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dataset_items",
        sa.Column("note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dataset_items", "note")
