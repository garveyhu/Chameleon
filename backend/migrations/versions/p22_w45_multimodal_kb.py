"""P22.4 PR #81+#82: documents.kind + chunks.kind + chunks.source_url

Revision ID: p22_w45_multimodal_kb
Revises: p22_w44_workflow_versioning
Create Date: 2027-03-29 12:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p22_w45_multimodal_kb"
down_revision: Union[str, Sequence[str], None] = "p22_w44_workflow_versioning"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            server_default="text",
        ),
    )
    op.add_column(
        "chunks",
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            server_default="text",
        ),
    )
    op.add_column(
        "chunks",
        sa.Column("source_url", sa.String(length=512), nullable=True),
    )
    op.create_index("ix_chunks_kind", "chunks", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_chunks_kind", table_name="chunks")
    op.drop_column("chunks", "source_url")
    op.drop_column("chunks", "kind")
    op.drop_column("documents", "kind")
