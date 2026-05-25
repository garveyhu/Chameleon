"""api_keys 留存明文（支持重复进来复制）

新增字段（nullable）：
- plain_key：签发时的明文 key 留存，便于在管理界面重复复制（产品取舍：便利
             优先于"仅一次回显"）。老数据为 NULL —— 仍只能看前缀，不回填。

安全提示：DB 因此持有可用密钥，库泄露即等同泄密；仅适用于单租户 / 内部场景。

Revision ID: p23_w56_apikey_plain
Revises: p23_w55_apikey_agent_scope
Create Date: 2026-05-25 20:05:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p23_w56_apikey_plain"
down_revision: Union[str, Sequence[str], None] = "p23_w55_apikey_agent_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("plain_key", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "plain_key")
