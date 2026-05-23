"""P19.4: messages.content_blocks JSONB 列（multimodal ContentBlock 协议）

老 messages.content 仍保留承载纯文本；多模态消息在 content_blocks 写完整
list[ContentBlock]，content 同时写 flattened 文本（兼容老消费者）。

Revision ID: p19_w23_message_blocks
Revises: p19_w21_workspaces
Create Date: 2026-05-23 13:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p19_w23_message_blocks"
down_revision: Union[str, Sequence[str], None] = "p19_w21_workspaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("content_blocks", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "content_blocks")
