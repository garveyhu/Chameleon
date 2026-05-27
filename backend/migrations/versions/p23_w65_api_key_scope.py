"""api_keys 作用域按域重构：agent_key → scope_type + scope_ref

原 agent_key 单字段硬塞作用域（NULL=应用级 / 非空=某 agent）。改为按领域：
scope_type ∈ app(通吃) / agent(某工作流) / kb(某知识库)，scope_ref 为域内目标。
回填：agent_key 非空 → (agent, agent_key)；空 → (app, NULL)。然后删 agent_key 列。

Revision ID: p23_w65_api_key_scope
Revises: p23_w64_chunk_content_search
Create Date: 2026-05-27 02:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p23_w65_api_key_scope"
down_revision: Union[str, Sequence[str], None] = "p23_w64_chunk_content_search"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column(
            "scope_type", sa.String(16), nullable=False, server_default="app"
        ),
    )
    op.add_column("api_keys", sa.Column("scope_ref", sa.String(128), nullable=True))
    # 回填：agent_key 非空 → agent 域
    op.execute(
        "UPDATE api_keys SET scope_type='agent', scope_ref=agent_key "
        "WHERE agent_key IS NOT NULL"
    )
    op.execute("CREATE INDEX ix_api_keys_scope ON api_keys (scope_type, scope_ref)")
    op.execute("DROP INDEX IF EXISTS ix_api_keys_agent")
    op.drop_column("api_keys", "agent_key")


def downgrade() -> None:
    op.add_column("api_keys", sa.Column("agent_key", sa.String(128), nullable=True))
    op.execute(
        "UPDATE api_keys SET agent_key=scope_ref WHERE scope_type='agent'"
    )
    op.execute("CREATE INDEX ix_api_keys_agent ON api_keys (agent_key)")
    op.execute("DROP INDEX IF EXISTS ix_api_keys_scope")
    op.drop_column("api_keys", "scope_ref")
    op.drop_column("api_keys", "scope_type")
