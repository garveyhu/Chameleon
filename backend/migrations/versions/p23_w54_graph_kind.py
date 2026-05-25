"""graph 形态区分：graphs 加 kind（chatflow / workflow）

新增字段（NOT NULL，server_default 'chatflow'）：
- kind：对话型 chatflow（有聊天 I/O、开场白、对话调试、可发布为智能体）
        vs 流程型 workflow（一次性管线、填输入表单跑、批处理）。

回填策略（老数据）：
- 默认置 workflow；
- 被某个 agent 关联（已发布为智能体）→ chatflow；
- spec 含 answer 节点（显式标注对话答案来源）→ chatflow。

Revision ID: p23_w54_graph_kind
Revises: p23_w53_agent_graph_id
Create Date: 2026-05-25 10:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p23_w54_graph_kind"
down_revision: Union[str, Sequence[str], None] = "p23_w53_agent_graph_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "graphs",
        sa.Column(
            "kind",
            sa.String(16),
            nullable=False,
            server_default="chatflow",
        ),
    )
    # 回填：默认流程型，再把对话型标回
    op.execute("UPDATE graphs SET kind = 'workflow'")
    op.execute(
        "UPDATE graphs SET kind = 'chatflow' "
        "WHERE id IN (SELECT graph_id FROM agents WHERE graph_id IS NOT NULL)"
    )
    op.execute(
        """
        UPDATE graphs SET kind = 'chatflow'
        WHERE kind <> 'chatflow'
          AND json_typeof(spec->'nodes') = 'array'
          AND EXISTS (
            SELECT 1 FROM json_array_elements(spec->'nodes') AS n
            WHERE n->>'type' = 'answer'
          )
        """
    )


def downgrade() -> None:
    op.drop_column("graphs", "kind")
