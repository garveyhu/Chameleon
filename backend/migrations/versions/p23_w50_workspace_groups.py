"""P23.C5: workspace_groups 计费分组 + group_ratio

新增：
- workspace_groups 表（code 唯一，ratio 成本倍率）+ 幂等 seed 4 个默认分组
- workspaces.group_code（FK workspace_groups.code ON DELETE SET NULL，默认 default）
- call_logs.group_ratio（写入时存死的分组倍率，effective cost = cost_usd × group_ratio）

红线：group_ratio 不进 cost_usd（cost_usd 存原始模型成本）；单独记到 call_log。

Revision ID: p23_w50_workspace_groups
Revises: p23_w49_calllog_dims
Create Date: 2026-05-24 12:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p23_w50_workspace_groups"
down_revision: Union[str, Sequence[str], None] = "p23_w49_calllog_dims"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_groups",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "ratio",
            sa.Numeric(6, 3),
            nullable=False,
            server_default="1.000",
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
        sa.UniqueConstraint("code", name="uq_workspace_groups_code"),
    )

    # 幂等 seed 默认分组（固定小 id，不与雪花 id 冲突）
    op.execute(
        """
        INSERT INTO workspace_groups (id, code, name, ratio)
        VALUES
            (1, 'default',  '默认',   1.000),
            (2, 'trial',    '试用',   2.000),
            (3, 'vip',      'VIP',    0.500),
            (4, 'internal', '内部',   0.000)
        ON CONFLICT (code) DO NOTHING
        """
    )

    op.add_column(
        "workspaces",
        sa.Column(
            "group_code",
            sa.String(length=32),
            nullable=True,
            server_default="default",
        ),
    )
    op.create_foreign_key(
        "fk_workspaces_group_code",
        "workspaces",
        "workspace_groups",
        ["group_code"],
        ["code"],
        ondelete="SET NULL",
    )

    op.add_column(
        "call_logs",
        sa.Column("group_ratio", sa.Numeric(6, 3), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("call_logs", "group_ratio")
    op.drop_constraint("fk_workspaces_group_code", "workspaces", type_="foreignkey")
    op.drop_column("workspaces", "group_code")
    op.drop_table("workspace_groups")
