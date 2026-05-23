"""P18.2: tool_instances 表 —— admin 配的工具运行时实例

业务：内置 Tool 类在代码层（chameleon.core.tools.builtins/*）；本表
存 admin 配的 (tool_key → config) + 启用开关。

Revision ID: p18_w12_tools
Revises: p18_w9_graphs
Create Date: 2026-05-23 19:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p18_w12_tools"
down_revision: Union[str, Sequence[str], None] = "p18_w9_graphs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tool_instances",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tool_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tool_key", name="uq_tool_instances_key"),
    )


def downgrade() -> None:
    op.drop_table("tool_instances")
