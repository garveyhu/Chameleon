"""P23.C7: channels 加多 key 池列 keys

新增 channels.keys（JSON，加密 key 字符串列表）；非空时路由走 key_pool 轮转，
空 / NULL 回退单 key（api_key_encrypted），老数据零迁移。

Revision ID: p23_w51_channel_keys
Revises: p23_w50_workspace_groups
Create Date: 2026-05-24 13:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p23_w51_channel_keys"
down_revision: Union[str, Sequence[str], None] = "p23_w50_workspace_groups"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("channels", sa.Column("keys", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("channels", "keys")
