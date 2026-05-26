"""agents 增加 model_bindings（agentkit 多具名模型槽绑定）

新增字段（nullable JSON）：
- model_bindings：{槽名: 已配置模型 code}，如 {"chat": "qwen-plus"}。
  仅 source='local' 的 @agent 智能体使用；web "关联模型" tab 写入，
  运行时 ctx.llm(slot) 读。老数据 NULL = 全部用槽 default / 系统默认。

Revision ID: p23_w58_agent_model_bindings
Revises: p23_w57_graphrun_session
Create Date: 2026-05-26 10:40:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p23_w58_agent_model_bindings"
down_revision: Union[str, Sequence[str], None] = "p23_w57_graphrun_session"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("model_bindings", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agents", "model_bindings")
