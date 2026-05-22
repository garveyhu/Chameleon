"""P16-C4: chunks.content_tsv GENERATED + GIN（关键词召回用）

Revision ID: p16c4_chunks_tsv
Revises: p16c_kb_dify
Create Date: 2026-05-22 22:00:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "p16c4_chunks_tsv"
down_revision: Union[str, Sequence[str], None] = "p16c_kb_dify"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # GENERATED 列必须先建（不能在 add_column 里给 generated 选项），用裸 SQL
    op.execute(
        "ALTER TABLE chunks ADD COLUMN content_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED"
    )
    op.execute(
        "CREATE INDEX ix_chunks_content_tsv "
        "ON chunks USING GIN (content_tsv)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_tsv")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS content_tsv")
