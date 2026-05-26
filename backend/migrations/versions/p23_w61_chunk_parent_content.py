"""chunks 增加 parent_content（parent-child 分层分块）

KB-P4-2：parent-child 分层。child 块精准召回，命中时返回所属 parent 大块作上下文。
- parent_content：child 所属的 parent 大块全文（NULL = 非分层块，按自身 content 返回）。
  inline 存储（不另起 parent 行）：写入简单、检索零额外查询，代价是同 parent 的多个
  child 各存一份 parent 文本（v1 取舍）。

Revision ID: p23_w61_chunk_parent_content
Revises: p23_w60_document_enabled
Create Date: 2026-05-26 15:10:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p23_w61_chunk_parent_content"
down_revision: Union[str, Sequence[str], None] = "p23_w60_document_enabled"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chunks", sa.Column("parent_content", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("chunks", "parent_content")
