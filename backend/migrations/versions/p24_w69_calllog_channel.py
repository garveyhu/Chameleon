"""块3: call_logs 加 channel 维度（会话账本调用来源渠道）

[SCHEMA-CHANGE] call_logs 新增 channel 列（api/openai/embed/playground/internal），
入口处盖章；会话账本按渠道筛选/溯源。NULL = 未标注（如图内部子观测、老数据）。

Revision ID: p24_w69_calllog_channel
Revises: p24_w68_drop_apps
Create Date: 2026-05-27 18:55:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p24_w69_calllog_channel"
down_revision: Union[str, Sequence[str], None] = "p24_w68_drop_apps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("call_logs", sa.Column("channel", sa.String(length=16), nullable=True))
    op.create_index(
        "ix_call_logs_channel_created", "call_logs", ["channel", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_call_logs_channel_created", table_name="call_logs")
    op.drop_column("call_logs", "channel")
