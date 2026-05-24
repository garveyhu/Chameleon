"""graph-agent: agents 加 graph_id（source='graph' 关联编排工作流）

新增字段（NULLABLE，老数据零迁移）：
- graph_id (BIGINT FK graphs.id ON DELETE SET NULL)：source='graph' 时关联的工作流；
  运行时服务该 graph 的 published_spec。

Revision ID: p23_w53_agent_graph_id
Revises: p23_w52_human_input_pending
Create Date: 2026-05-24 22:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p23_w53_agent_graph_id"
down_revision: Union[str, Sequence[str], None] = "p23_w52_human_input_pending"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("graph_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_agents_graph",
        "agents",
        "graphs",
        ["graph_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_agents_graph", "agents", type_="foreignkey")
    op.drop_column("agents", "graph_id")
