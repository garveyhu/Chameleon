"""P17.A1.2 mini: agents 表新增 preferred_model_code

为路由 service 给 agent 声明"我需要什么能力"留位置。NULL 表示 agent 不参与
矩阵路由（fallback 老的 agent.provider 直绑）。

Revision ID: p17_w4_agent_model_code
Revises: p17_w4_abilities
Create Date: 2026-05-24 02:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p17_w4_agent_model_code"
down_revision: Union[str, Sequence[str], None] = "p17_w4_abilities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("preferred_model_code", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agents", "preferred_model_code")
