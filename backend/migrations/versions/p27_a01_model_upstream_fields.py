"""models 加 upstream_name / upstream_group / capabilities（new-api 网关收口）

[SCHEMA-CHANGE] 逻辑模型目录化第一步：逻辑模型(code) 与 上游模型名(upstream_name)
解耦，为"new-api 当统一网关"铺路。三列全 NULL 时行为与现状 100% 一致
（factory 回退用 code），纯向后兼容。

- upstream_name  VARCHAR(128) NULL：打给 new-api 的模型名；NULL → 回退 code
- upstream_group VARCHAR(64)  NULL：对应 new-api 的 group；NULL → 默认组（预留）
- capabilities   JSON         NULL：{vision, rerank, function_calling,
                                     context_window, max_output} —— 驱动 UI/选择器，与计费无关

Revision ID: p27_a01_model_upstream_fields
Revises: p26_g01_run_item_judge_fields
Create Date: 2026-06-04
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "p27_a01_model_upstream_fields"
down_revision: Union[str, Sequence[str], None] = "p26_g01_run_item_judge_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "models",
        sa.Column(
            "upstream_name",
            sa.String(length=128),
            nullable=True,
            comment="打给上游网关(new-api)的模型名；NULL 时工厂回退用 code",
        ),
    )
    op.add_column(
        "models",
        sa.Column(
            "upstream_group",
            sa.String(length=64),
            nullable=True,
            comment="对应 new-api 的 group；NULL=默认组（预留）",
        ),
    )
    op.add_column(
        "models",
        sa.Column(
            "capabilities",
            sa.JSON(),
            nullable=True,
            comment="能力元数据 {vision, rerank, function_calling, context_window, max_output}",
        ),
    )


def downgrade() -> None:
    op.drop_column("models", "capabilities")
    op.drop_column("models", "upstream_group")
    op.drop_column("models", "upstream_name")
