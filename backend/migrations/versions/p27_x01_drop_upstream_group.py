"""models 删除 upstream_group（死字段，从未被工厂读取路由）

[SCHEMA-CHANGE] p27_a01 预留的 upstream_group 始终未接入路由（new-api 分组路由靠
token 绑定 group，不在 per-request），属存而不用的死列，移除以免误导。upstream_name
（逻辑 code↔上游名解耦）保留。

Revision ID: p27_x01_drop_upstream_group
Revises: p27_c01_run_item_reqid
Create Date: 2026-06-05
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "p27_x01_drop_upstream_group"
down_revision: Union[str, Sequence[str], None] = "p27_c01_run_item_reqid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("models", "upstream_group")


def downgrade() -> None:
    op.add_column(
        "models",
        sa.Column(
            "upstream_group",
            sa.String(length=64),
            nullable=True,
            comment="对应 new-api 的 group；NULL=默认组（预留）",
        ),
    )
