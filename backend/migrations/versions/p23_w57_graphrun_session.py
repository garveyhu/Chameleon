"""graph_runs 加 session_id（对话会话标识）

新增字段（nullable）：
- session_id：chat 多轮同属一个 session_id，便于在运行日志里按会话归类 / 标识；
             admin 控制台手动跑无会话 → None。老数据不回填。

Revision ID: p23_w57_graphrun_session
Revises: p23_w56_apikey_plain
Create Date: 2026-05-25 20:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p23_w57_graphrun_session"
down_revision: Union[str, Sequence[str], None] = "p23_w56_apikey_plain"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "graph_runs",
        sa.Column("session_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_graph_runs_session", "graph_runs", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_graph_runs_session", table_name="graph_runs")
    op.drop_column("graph_runs", "session_id")
