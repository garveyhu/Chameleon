"""模块 H3：dataset_runs 加优化产出 + 自引用版本链

落库口径（与 ORM dataset.py DatasetRun 对齐）：
- optimized_prompt（Text）：LLM 重写产出，挂在「被优化的 run」上
- optimization_report（JSON）：结构化报告，给未来多版本 / 进度态留弹性
- parent_run_id（BigInteger，自引用 FK，SET NULL）：版本链——本 run 由哪个 run 优化而来

全 nullable，存量零影响。自引用 FK 用 SET NULL（删父 run 不连带删子版本，保留谱系断点）。
down_revision 挂 p27_g02_ref_judge_config，保持线性单 head（不碰 newapi 字段）。

Revision ID: p27_h01_run_lineage
Revises: p27_g02_ref_judge_config
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "p27_h01_run_lineage"
down_revision: Union[str, Sequence[str], None] = "p27_g02_ref_judge_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dataset_runs",
        sa.Column("optimized_prompt", sa.Text(), nullable=True),
    )
    op.add_column(
        "dataset_runs",
        sa.Column("optimization_report", sa.JSON(), nullable=True),
    )
    op.add_column(
        "dataset_runs",
        sa.Column("parent_run_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_dataset_runs_parent",
        "dataset_runs",
        "dataset_runs",
        ["parent_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_dataset_runs_parent",
        "dataset_runs",
        ["parent_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_dataset_runs_parent", table_name="dataset_runs")
    op.drop_constraint(
        "fk_dataset_runs_parent", "dataset_runs", type_="foreignkey"
    )
    op.drop_column("dataset_runs", "parent_run_id")
    op.drop_column("dataset_runs", "optimization_report")
    op.drop_column("dataset_runs", "optimized_prompt")
