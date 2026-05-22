"""P17.C1: call_logs 扩展为嵌套 Observation

新增字段：
- parent_id (VARCHAR(64))：同表 request_id 自引；NULL = trace root
- observation_type (VARCHAR(32))：trace/span/generation/agent/tool/
  retriever/evaluator/embedding/guardrail；默认 generation 兼容老数据
- completion_start_ms (INT)：流式首 token 延迟

加索引：parent_id（trace tree 子节点扫）+ observation_type（按类型聚合）

Revision ID: p17_w6_observation
Revises: p17_w4_agent_model_code
Create Date: 2026-05-23 12:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p17_w6_observation"
down_revision: Union[str, Sequence[str], None] = "p17_w4_agent_model_code"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "call_logs",
        sa.Column("parent_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "call_logs",
        sa.Column(
            "observation_type",
            sa.String(length=32),
            nullable=False,
            server_default="generation",
        ),
    )
    op.add_column(
        "call_logs",
        sa.Column("completion_start_ms", sa.Integer(), nullable=True),
    )
    op.create_index("ix_call_logs_parent", "call_logs", ["parent_id"])
    op.create_index("ix_call_logs_type", "call_logs", ["observation_type"])


def downgrade() -> None:
    op.drop_index("ix_call_logs_type", table_name="call_logs")
    op.drop_index("ix_call_logs_parent", table_name="call_logs")
    op.drop_column("call_logs", "completion_start_ms")
    op.drop_column("call_logs", "observation_type")
    op.drop_column("call_logs", "parent_id")
