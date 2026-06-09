"""agent_memory_vector 表（agentkit ctx.memory.search 语义召回底座）

T1-1 memory 升级 M1：与 agent_memory（KV 真相源）旁路并存。memory.set 时把值文本投影
embed 入本表，memory.search 按 (agent_key, scope_ref) 隔离做 vector+BM25 hybrid 召回。
content_tsv（GENERATED，优先切词列）+ GIN 给中文 BM25；HNSW(cosine) 给向量召回。

Revision ID: p27_x10_agent_memory_vector
Revises: 3665cec8fcd2
Create Date: 2026-06-09 13:30:00
"""

from typing import Sequence, Union

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

revision: str = "p27_x10_agent_memory_vector"
down_revision: Union[str, Sequence[str], None] = "3665cec8fcd2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_memory_vector",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("agent_key", sa.String(length=128), nullable=False),
        sa.Column("scope_ref", sa.String(length=128), nullable=False),
        sa.Column("mkey", sa.String(length=128), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_search", sa.Text(), nullable=True),
        sa.Column(
            "embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "agent_key", "scope_ref", "mkey", name="uq_agent_memory_vector_key"
        ),
    )
    op.create_index(
        "ix_agent_memory_vector_scope",
        "agent_memory_vector",
        ["agent_key", "scope_ref"],
    )
    # content_tsv GENERATED（中文 BM25：优先 jieba 切词列，回退原文）+ GIN
    op.execute(
        "ALTER TABLE agent_memory_vector ADD COLUMN content_tsv tsvector "
        "GENERATED ALWAYS AS "
        "(to_tsvector('simple', coalesce(text_search, text))) STORED"
    )
    op.execute(
        "CREATE INDEX ix_agent_memory_vector_tsv "
        "ON agent_memory_vector USING GIN (content_tsv)"
    )
    # HNSW 向量索引（cosine），与 chunks 同参数
    op.execute(
        "CREATE INDEX ix_agent_memory_vector_embed ON agent_memory_vector "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_memory_vector_embed")
    op.execute("DROP INDEX IF EXISTS ix_agent_memory_vector_tsv")
    op.drop_index(
        "ix_agent_memory_vector_scope", table_name="agent_memory_vector"
    )
    op.drop_table("agent_memory_vector")
