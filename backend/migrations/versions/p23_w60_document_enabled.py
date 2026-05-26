"""documents 增加文档级启停字段 enabled

KB-P2：文档列表增强。
- enabled：文档级启停（默认 true）；enabled=false 时整篇文档的 chunk 不参与检索。
  与 chunk.enabled 叠加——任一为 false 即不召回。

Revision ID: p23_w60_document_enabled
Revises: p23_w59_chunk_segment_mgmt
Create Date: 2026-05-26 14:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p23_w60_document_enabled"
down_revision: Union[str, Sequence[str], None] = "p23_w59_chunk_segment_mgmt"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default="true"
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "enabled")
