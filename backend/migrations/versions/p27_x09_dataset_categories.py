"""数据集能力维度 + 样本归类

- datasets.categories (JSON)：数据集定义的能力维度 [{key,label,description}]，
  取代前端硬编码关键词猜测；对比雷达的轴 + 样本归类据此而来。
- dataset_items.category (String)：样本归属的维度 key（单维度）。

down_revision 挂 p27_x06_ai_tasks（agentkit 的 x07/x08 不在本分支），线性单 head。

Revision ID: p27_x09_dataset_categories
Revises: p27_x06_ai_tasks
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "p27_x09_dataset_categories"
down_revision: Union[str, Sequence[str], None] = "p27_x06_ai_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("categories", sa.JSON(), nullable=True))
    op.add_column(
        "dataset_items", sa.Column("category", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("dataset_items", "category")
    op.drop_column("datasets", "categories")
