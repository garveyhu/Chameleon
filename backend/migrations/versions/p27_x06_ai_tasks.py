"""ai_tasks 表 —— 系统内各种 AI 任务的统一存储（异步执行 + 状态跟踪 + 结果缓存）

落库口径（与 ORM ai_task.py AiTask 对齐）：
- 配合 chameleon-aikit 执行层：aikit 跑 LLM，ai_tasks 负责异步调度 + 存状态/结果 + 缓存去重。
- input_hash 索引用于缓存命中查找；(scope, scope_ref) 索引用于按业务归属列出历史任务。
- task_type 对齐 aikit registry key。

down_revision 挂 p27_x05_dataset_item_note，保持线性单 head。

Revision ID: p27_x06_ai_tasks
Revises: p27_x05_dataset_item_note
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "p27_x06_ai_tasks"
down_revision: Union[str, Sequence[str], None] = "p27_x05_dataset_item_note"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_tasks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=True),
        sa.Column("scope_ref", sa.String(length=128), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("input", sa.JSON(), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="pending"
        ),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("model_code", sa.String(length=64), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_tasks_input_hash", "ai_tasks", ["input_hash"])
    op.create_index("ix_ai_tasks_scope", "ai_tasks", ["scope", "scope_ref"])


def downgrade() -> None:
    op.drop_index("ix_ai_tasks_scope", table_name="ai_tasks")
    op.drop_index("ix_ai_tasks_input_hash", table_name="ai_tasks")
    op.drop_table("ai_tasks")
