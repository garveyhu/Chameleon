"""会话附件 + 临时 KB（Phase B）：session_files 表 + knowledge_bases.kind

[SCHEMA-CHANGE] 新建 session_files 表，记录会话上下文里的所有附件（图/音/文档/数据）；
                knowledge_bases 加 kind 字段（normal | ephemeral_session）。

设计：
- session_files 是「会话 ↔ 文件 ↔ 临时 KB」的桥；document_id 关联到 KB 的 Document 行
  让现成的 KB 切块/向量化/检索 pipeline 直接复用。
- ephemeral_session 类 KB 不出现在常规 KB 列表（按 kind 过滤），由 session 软删时
  级联清理（业务层；不靠 DB FK，方便手动清孤儿）。

Revision ID: p25_b01_session_files
Revises: p25_a01_session_redesign
Create Date: 2026-05-28 19:00:00
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "p25_b01_session_files"
down_revision: Union[str, Sequence[str], None] = "p25_a01_session_redesign"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. knowledge_bases 加 kind 字段（区分常规 / 会话临时） ──────────
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "kind",
            sa.String(length=24),
            nullable=False,
            server_default="normal",
        ),
    )
    op.create_index(
        "ix_knowledge_bases_kind",
        "knowledge_bases",
        ["kind"],
    )

    # ── 2. session_files 表 ──────────────────────────────────────────
    op.create_table(
        "session_files",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column(
            "end_user_id",
            sa.String(length=128),
            nullable=True,
            comment="冗余 session.end_user_id 便于按用户查",
        ),
        sa.Column("object_url", sa.Text(), nullable=False),
        sa.Column("object_id", sa.String(length=255), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime", sa.String(length=128), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "kind",
            sa.String(length=24),
            nullable=False,
            comment="image / audio / document / data / other",
        ),
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
            comment="document 类型时关联到 KB 文档行（复用 KB 切块 / 检索 pipeline）",
        ),
        sa.Column(
            "ephemeral_kb_id",
            sa.BigInteger(),
            sa.ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
            nullable=True,
            comment="document/data 类型时关联到临时 KB（kind=ephemeral_session）",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="uploaded",
            comment="uploaded / parsing / ready / failed",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_session_files_session", "session_files", ["session_id"])
    op.create_index("ix_session_files_end_user", "session_files", ["end_user_id"])
    op.create_index("ix_session_files_kind", "session_files", ["kind"])
    op.create_index("ix_session_files_status", "session_files", ["status"])
    op.create_index("ix_session_files_created", "session_files", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_session_files_created", table_name="session_files")
    op.drop_index("ix_session_files_status", table_name="session_files")
    op.drop_index("ix_session_files_kind", table_name="session_files")
    op.drop_index("ix_session_files_end_user", table_name="session_files")
    op.drop_index("ix_session_files_session", table_name="session_files")
    op.drop_table("session_files")

    op.drop_index("ix_knowledge_bases_kind", table_name="knowledge_bases")
    op.drop_column("knowledge_bases", "kind")
