"""agents 增加 tool_bindings 列（agentkit 平台工具启用集）

agentkit P0-1：@agent(tools=[...]) 声明平台工具可用集，web「关联工具」tab 写入
已启用的 tool_key 子集到 agents.tool_bindings（JSON list）。None = 声明的工具全
启用；列表 = 启用子集，运行时 runner 取交集后绑定到 LLM。

Revision ID: p27_x07_agent_tool_bindings
Revises: p27_x06_ai_tasks
Create Date: 2026-06-08 02:10:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p27_x07_agent_tool_bindings"
down_revision: Union[str, Sequence[str], None] = "p27_x06_ai_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("tool_bindings", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agents", "tool_bindings")
