"""P16-C: KB Dify-grade schema (documents/kbs ext + agent_kb_link + retrieval_evaluation)

Revision ID: p16c_kb_dify
Revises: p16a_model_defaults
Create Date: 2026-05-22 18:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p16c_kb_dify"
down_revision: Union[str, Sequence[str], None] = "p16a_model_defaults"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── knowledge_bases 扩字段 ──────────────────────────────────────
    # chunk_strategy JSON 默认带 ":" → 绕开 SA text() 的冒号 bind 解析；
    # 先 nullable=True 加列，再用 bind-param UPDATE 写默认，再设 NOT NULL。
    op.add_column(
        "knowledge_bases",
        sa.Column("chunk_strategy", sa.JSON(), nullable=True),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "default_top_k",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("5"),
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "recall_mode",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'vector'"),
        ),
    )
    conn.execute(
        sa.text(
            "UPDATE knowledge_bases SET chunk_strategy = CAST(:v AS json) "
            "WHERE chunk_strategy IS NULL"
        ).bindparams(v='{"mode":"fixed","chunk_size":800,"overlap":100}')
    )
    op.alter_column("knowledge_bases", "chunk_strategy", nullable=False)

    # ── documents 扩字段 ────────────────────────────────────────────
    op.add_column(
        "documents",
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "chunk_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "token_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "tags",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    # 同 KB 的 chunk_strategy，可为 null（表示沿用 KB 级配置）
    op.add_column(
        "documents",
        sa.Column("chunk_strategy", sa.JSON(), nullable=True),
    )

    # ── agent_kb_link ───────────────────────────────────────────────
    op.create_table(
        "agent_kb_link",
        sa.Column("agent_id", sa.BigInteger(), nullable=False),
        sa.Column("kb_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("agent_id", "kb_id"),
    )
    op.create_index("ix_agent_kb_link_kb", "agent_kb_link", ["kb_id"], unique=False)

    # ── retrieval_evaluation ────────────────────────────────────────
    op.create_table(
        "retrieval_evaluation",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("kb_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("queries", sa.JSON(), nullable=False),
        sa.Column("results", sa.JSON(), nullable=True),
        sa.Column("recall_mode", sa.String(length=16), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_retrieval_evaluation_kb_created",
        "retrieval_evaluation",
        ["kb_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_retrieval_evaluation_kb_created", table_name="retrieval_evaluation"
    )
    op.drop_table("retrieval_evaluation")
    op.drop_index("ix_agent_kb_link_kb", table_name="agent_kb_link")
    op.drop_table("agent_kb_link")

    op.drop_column("documents", "chunk_strategy")
    op.drop_column("documents", "tags")
    op.drop_column("documents", "token_count")
    op.drop_column("documents", "chunk_count")
    op.drop_column("documents", "size_bytes")

    op.drop_column("knowledge_bases", "recall_mode")
    op.drop_column("knowledge_bases", "default_top_k")
    op.drop_column("knowledge_bases", "chunk_strategy")
