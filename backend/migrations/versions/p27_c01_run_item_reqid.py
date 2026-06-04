"""Phase C：dataset_run_items 加 request_id（样本级 trace 下钻地基）

落库口径（与 ORM dataset.py DatasetRunItem 对齐）：
- request_id（String(64), nullable）：本 item 这次执行的 request_id，被测 LLM /
  agent 的 generation·embedding·retriever 子观测均以此盖章（channel='eval'），也是
  eval 根 trace 行的 request_id。

样本详情据此直达 /traces/{request_id} 看真实 LLM 调用。全 nullable，旧数据零影响
（迁移前已跑的 run item 该列为 NULL，前端按 None 隐藏 trace 入口）。
down_revision 挂 p27_h01_run_lineage，保持线性单 head（不碰 newapi 字段）。

Revision ID: p27_c01_run_item_reqid
Revises: p27_h01_run_lineage
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "p27_c01_run_item_reqid"
down_revision: Union[str, Sequence[str], None] = "p27_h01_run_lineage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dataset_run_items",
        sa.Column("request_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dataset_run_items", "request_id")
