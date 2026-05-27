"""chunks 增加 content_search（jieba 切词）+ content_tsv 改从切词列生成

中文关键词召回修复：PG 'simple' ts 配置不切中文，整段中文成一个 token，中文 BM25
形同虚设。新增 content_search 存 jieba 切词后的文本（应用层写），content_tsv 改为
to_tsvector('simple', coalesce(content_search, content))——有切词用切词（中文词级），
老块 content_search 为 NULL 时回退原始 content（不回归英文召回）。

Revision ID: p23_w64_chunk_content_search
Revises: p23_w63_kb_icon
Create Date: 2026-05-27 01:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p23_w64_chunk_content_search"
down_revision: Union[str, Sequence[str], None] = "p23_w63_kb_icon"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("content_search", sa.Text(), nullable=True))
    # 重建 GENERATED content_tsv：优先用切词列，回退原始 content
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_tsv")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS content_tsv")
    op.execute(
        "ALTER TABLE chunks ADD COLUMN content_tsv tsvector "
        "GENERATED ALWAYS AS "
        "(to_tsvector('simple', coalesce(content_search, content))) STORED"
    )
    op.execute(
        "CREATE INDEX ix_chunks_content_tsv ON chunks USING GIN (content_tsv)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_tsv")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS content_tsv")
    op.execute(
        "ALTER TABLE chunks ADD COLUMN content_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED"
    )
    op.execute(
        "CREATE INDEX ix_chunks_content_tsv ON chunks USING GIN (content_tsv)"
    )
    op.drop_column("chunks", "content_search")
