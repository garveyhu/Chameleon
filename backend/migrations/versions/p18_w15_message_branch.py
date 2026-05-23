"""P18.5 PR #27: messages 加 parent_message_id 支持分支

业务：regenerate / edit-and-resend 时不覆盖老 assistant，而是新增一条
parent_message_id 指向 fork 起点的消息。前端 tree 视图按 parent_message_id
聚类显示主线 + 分支。

Revision ID: p18_w15_message_branch
Revises: p18_w13_dataset_runs
Create Date: 2026-05-23 20:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p18_w15_message_branch"
down_revision: Union[str, Sequence[str], None] = "p18_w13_dataset_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("parent_message_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_messages_parent", "messages", ["parent_message_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_messages_parent", table_name="messages")
    op.drop_column("messages", "parent_message_id")
