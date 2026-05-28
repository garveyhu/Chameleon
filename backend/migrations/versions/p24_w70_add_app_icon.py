"""应用头像：agents / graphs 加 icon 列（用户上传图片缩放后的 data URL）

[SCHEMA-CHANGE] agents.icon / graphs.icon 新增 Text 列，存头像 data URL；
NULL = 用默认按类型图标。应用卡片与编辑弹窗读写。

Revision ID: p24_w70_add_app_icon
Revises: p24_w69_calllog_channel
Create Date: 2026-05-28 10:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p24_w70_add_app_icon"
down_revision: Union[str, Sequence[str], None] = "p24_w69_calllog_channel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("icon", sa.Text(), nullable=True))
    op.add_column("graphs", sa.Column("icon", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("graphs", "icon")
    op.drop_column("agents", "icon")
