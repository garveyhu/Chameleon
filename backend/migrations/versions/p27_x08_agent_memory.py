"""agent_memory 表（agentkit ctx.memory kv 记忆）

agentkit P1-3：ctx.memory.get/set/all 的 kv 持久化。按 (agent_key, scope_ref, mkey)
唯一；scope_ref 优先 end_user_id（跨会话），无身份退化 session_id。

Revision ID: p27_x08_agent_memory
Revises: p27_x07_agent_tool_bindings
Create Date: 2026-06-08 03:15:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p27_x08_agent_memory"
down_revision: Union[str, Sequence[str], None] = "p27_x07_agent_tool_bindings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_memory",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("agent_key", sa.String(length=128), nullable=False),
        sa.Column("scope_ref", sa.String(length=128), nullable=False),
        sa.Column("mkey", sa.String(length=128), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "agent_key", "scope_ref", "mkey", name="uq_agent_memory_key"
        ),
    )
    op.create_index("ix_agent_memory_agent_key", "agent_memory", ["agent_key"])


def downgrade() -> None:
    op.drop_index("ix_agent_memory_agent_key", table_name="agent_memory")
    op.drop_table("agent_memory")
