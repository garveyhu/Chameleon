"""knowledge_bases 增加自定义图标 icon

KB 编辑支持上传自定义图标（base64 data URL，小图）；缺省走前端默认图标。

Revision ID: p23_w63_kb_icon
Revises: p23_w62_kb_metadata_fields
Create Date: 2026-05-27 00:50:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p23_w63_kb_icon"
down_revision: Union[str, Sequence[str], None] = "p23_w62_kb_metadata_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column("icon", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_bases", "icon")
