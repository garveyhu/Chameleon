"""会话附件解耦知识库：session_files 加 parsed_text + 新建 session_file_chunks

[SCHEMA-CHANGE] 临时上传文件不再创建 ephemeral KB（业界共识：知识库是用户手动维护的资产）。
                改为：小文件全文塞 system prompt；大文件切块到独立 session_file_chunks 表。

变更：
1. session_files 加列：parsed_text (TEXT)、text_size (INT)、use_full_text (BOOL DEFAULT TRUE)
2. 新建 session_file_chunks 表：id / session_file_id / session_id / ord_index / content /
   embedding vector(1536) / tokens / created_at / updated_at / deleted_at
   建 ivfflat (vector_cosine_ops) 向量索引
3. 软删现有 kind='ephemeral_session' 的 KB 行（业务上已停用，避免出现在用户的 KB 列表里）
4. ephemeral_kb_id / document_id 字段不删（向后兼容，service 不再写新值）

Revision ID: p26_a01_session_files_v2
Revises: p25_b01_session_files
Create Date: 2026-05-28 21:50:00
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "p26_a01_session_files_v2"
down_revision: Union[str, Sequence[str], None] = "p25_b01_session_files"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. session_files 加列 ────────────────────────────────────────
    op.add_column(
        "session_files",
        sa.Column(
            "parsed_text",
            sa.Text(),
            nullable=True,
            comment="小文件全文（use_full_text=true 时填）",
        ),
    )
    op.add_column(
        "session_files",
        sa.Column(
            "text_size",
            sa.Integer(),
            nullable=True,
            comment="解析后文本字符数（用于路由小文件 / 大文件）",
        ),
    )
    op.add_column(
        "session_files",
        sa.Column(
            "use_full_text",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
            comment="true=小文件全文喂 prompt；false=已切块到 session_file_chunks 走向量",
        ),
    )

    # ── 2. session_file_chunks（独立于 KB 域） ────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.create_table(
        "session_file_chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "session_file_id",
            sa.BigInteger(),
            sa.ForeignKey("session_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("ord_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        # pgvector 1536 维（对齐 OpenAI text-embedding-3-small / ada-002）
        sa.Column(
            "embedding",
            sa.dialects.postgresql.ARRAY(sa.Float()),  # placeholder，下方 ALTER 改 vector
            nullable=False,
        ),
        sa.Column("tokens", sa.Integer(), nullable=False, server_default="0"),
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
    # 用 raw SQL 把 embedding 改成 pgvector 的 vector 类型（alembic 不直接支持 vector(N)）
    op.execute("ALTER TABLE session_file_chunks ALTER COLUMN embedding TYPE vector(1536) USING NULL;")
    # 索引
    op.execute(
        "CREATE INDEX ix_sfc_session ON session_file_chunks(session_id) "
        "WHERE deleted_at IS NULL;"
    )
    op.execute("CREATE INDEX ix_sfc_file ON session_file_chunks(session_file_id);")
    op.execute("CREATE INDEX ix_sfc_created ON session_file_chunks(created_at);")
    # 向量索引（ivfflat / cosine），lists=50 适合中等规模
    op.execute(
        "CREATE INDEX ix_sfc_embedding ON session_file_chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);"
    )

    # ── 3. 软删历史 ephemeral KB（业务停用，但保留行/字段不动） ──────────
    op.execute(
        "UPDATE knowledge_bases SET deleted_at = CURRENT_TIMESTAMP "
        "WHERE kind = 'ephemeral_session' AND deleted_at IS NULL;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sfc_embedding;")
    op.execute("DROP INDEX IF EXISTS ix_sfc_created;")
    op.execute("DROP INDEX IF EXISTS ix_sfc_file;")
    op.execute("DROP INDEX IF EXISTS ix_sfc_session;")
    op.drop_table("session_file_chunks")

    op.drop_column("session_files", "use_full_text")
    op.drop_column("session_files", "text_size")
    op.drop_column("session_files", "parsed_text")
