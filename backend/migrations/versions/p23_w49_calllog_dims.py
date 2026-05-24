"""P23.C1: call_logs 加计费多维列 user_id / model_code / channel_id

新增字段（全 NULLABLE，老数据零迁移升级）：
- user_id (BIGINT FK users.id ON DELETE SET NULL)：发起调用的用户
- model_code (VARCHAR(64))：实际命中的模型编码（路由后）
- channel_id (BIGINT FK channels.id ON DELETE SET NULL)：实际命中的上游 channel

加复合索引（C8 cost dashboard 按维度在时间窗内聚合）：
- (user_id, created_at) / (model_code, created_at) / (channel_id, created_at)

Revision ID: p23_w49_calllog_dims
Revises: p22_w47_app_templates
Create Date: 2026-05-24 10:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p23_w49_calllog_dims"
down_revision: Union[str, Sequence[str], None] = "p22_w47_app_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "call_logs",
        sa.Column("user_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "call_logs",
        sa.Column("model_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "call_logs",
        sa.Column("channel_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_call_logs_user",
        "call_logs",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_call_logs_channel",
        "call_logs",
        "channels",
        ["channel_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_call_logs_user_created", "call_logs", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_call_logs_model_created", "call_logs", ["model_code", "created_at"]
    )
    op.create_index(
        "ix_call_logs_channel_created", "call_logs", ["channel_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_call_logs_channel_created", table_name="call_logs")
    op.drop_index("ix_call_logs_model_created", table_name="call_logs")
    op.drop_index("ix_call_logs_user_created", table_name="call_logs")
    op.drop_constraint("fk_call_logs_channel", "call_logs", type_="foreignkey")
    op.drop_constraint("fk_call_logs_user", "call_logs", type_="foreignkey")
    op.drop_column("call_logs", "channel_id")
    op.drop_column("call_logs", "model_code")
    op.drop_column("call_logs", "user_id")
