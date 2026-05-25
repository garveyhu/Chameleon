"""api_keys 加 agent_key（智能体级作用域）

新增字段（nullable）：
- agent_key：None = 应用级密钥（对所有端点 / 所有 agent 有效，老语义不变）；
             非空 = 智能体级密钥，仅对该 agent_key 的 /agents/{key}/invoke
             与 /chat/completions 有效（编辑器「管理密钥」生成的就是这种）。

老数据无需回填（NULL 即应用级，保持现状）。

Revision ID: p23_w55_apikey_agent_scope
Revises: p23_w54_graph_kind
Create Date: 2026-05-25 19:40:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p23_w55_apikey_agent_scope"
down_revision: Union[str, Sequence[str], None] = "p23_w54_graph_kind"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("agent_key", sa.String(128), nullable=True),
    )
    op.create_index("ix_api_keys_agent", "api_keys", ["agent_key"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_agent", table_name="api_keys")
    op.drop_column("api_keys", "agent_key")
