"""messages 加 request_id 字段：反馈按钮按它落 score 表关联 trace

[SCHEMA-CHANGE] messages 表加 request_id VARCHAR(64) NULL + 索引。

业务变化：之前 message 行不存 trace_id，widget 历史回放时反馈按钮无法落
到具体 trace，只能本地切 active 不入库。现在 invoke / stream 写消息时一并
落 rid，历史回放也能反馈到 score 表。

Revision ID: p26_b01_msg_request_id
Revises: p26_a01_session_files_v2
Create Date: 2026-05-28 23:55:00
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "p26_b01_msg_request_id"
down_revision: Union[str, Sequence[str], None] = "p26_a01_session_files_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "request_id",
            sa.String(length=64),
            nullable=True,
            comment="本条消息所属调用的 trace_id（= request_id），widget 反馈按它落 score",
        ),
    )
    op.create_index("ix_messages_request_id", "messages", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_request_id", table_name="messages")
    op.drop_column("messages", "request_id")
