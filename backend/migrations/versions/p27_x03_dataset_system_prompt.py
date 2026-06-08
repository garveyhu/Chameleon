"""datasets 加 system_prompt（数据集级默认系统提示词）

落库口径（与 ORM dataset.py Dataset 对齐）：
- system_prompt（Text, nullable）：数据集固有的系统提示词（如 text2sql 的库表 schema +
  「只输出 SQL」指令）。运行评估时作为被测模型的 system 默认值，wizard 预填、可逐次覆盖。

全 nullable，旧数据零影响（迁移前的数据集该列 NULL，运行不带 prompt_override 即与旧行为一致）。
down_revision 挂 p27_x02_media_pricing，保持线性单 head。

Revision ID: p27_x03_dataset_system_prompt
Revises: p27_x02_media_pricing
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "p27_x03_dataset_system_prompt"
down_revision: Union[str, Sequence[str], None] = "p27_x02_media_pricing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "datasets",
        sa.Column("system_prompt", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("datasets", "system_prompt")
