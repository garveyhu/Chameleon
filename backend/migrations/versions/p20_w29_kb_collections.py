"""P20.3: kb_collections 表 + chunks 加 collection_id / index_name / qa_question / api_endpoint

业务：每个 KB 可挂 N 个 collection（chunker 类型 + 索引拓扑）；
collection_type 一经写入不可改（service 层守卫），改类型 = 新建 collection。

老 chunks.collection_id = NULL，retrieve 路径仍 by kb_id 工作；后续 admin
重新 ingest 才会落到具体 collection_id。

Revision ID: p20_w29_kb_collections
Revises: p20_w27_plugin_registries
Create Date: 2026-12-06 12:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p20_w29_kb_collections"
down_revision: Union[str, Sequence[str], None] = "p20_w27_plugin_registries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kb_collections",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "kb_id",
            sa.BigInteger(),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "collection_type",
            sa.String(length=16),
            nullable=False,
            server_default="generic",
        ),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("indexes", sa.JSON(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_kb_collections_kb", "kb_collections", ["kb_id"])

    # chunks 加列
    op.add_column(
        "chunks",
        sa.Column(
            "collection_id",
            sa.BigInteger(),
            sa.ForeignKey("kb_collections.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "chunks",
        sa.Column(
            "index_name",
            sa.String(length=32),
            nullable=False,
            server_default="chunk",
        ),
    )
    op.add_column("chunks", sa.Column("qa_question", sa.Text(), nullable=True))
    op.add_column(
        "chunks", sa.Column("api_endpoint", sa.String(length=256), nullable=True)
    )
    op.create_index(
        "ix_chunks_collection_index", "chunks", ["collection_id", "index_name"]
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_collection_index", table_name="chunks")
    op.drop_column("chunks", "api_endpoint")
    op.drop_column("chunks", "qa_question")
    op.drop_column("chunks", "index_name")
    op.drop_column("chunks", "collection_id")
    op.drop_index("ix_kb_collections_kb", table_name="kb_collections")
    op.drop_table("kb_collections")
