"""新增 kb_metadata_fields 表（KB-P5 元数据字段体系）

KB 级字段定义（key/label/类型/选项）；每文档在 Document.meta 按 key 存值，
检索可按字段值过滤召回。

Revision ID: p23_w62_kb_metadata_fields
Revises: p23_w61_chunk_parent_content
Create Date: 2026-05-26 16:40:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p23_w62_kb_metadata_fields"
down_revision: Union[str, Sequence[str], None] = "p23_w61_chunk_parent_content"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kb_metadata_fields",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("kb_id", sa.BigInteger(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column(
            "field_type",
            sa.String(length=16),
            nullable=False,
            server_default="string",
        ),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("kb_id", "key", name="uq_kb_metadata_fields_kb_key"),
    )
    op.create_index(
        "ix_kb_metadata_fields_kb", "kb_metadata_fields", ["kb_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_kb_metadata_fields_kb", table_name="kb_metadata_fields")
    op.drop_table("kb_metadata_fields")
