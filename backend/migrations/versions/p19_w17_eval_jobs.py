"""P19.1: eval_jobs + eval_job_runs 表

业务：把 (dataset, judge, target) 打包成 cron 触发的 Eval 任务，做"每日基线回归"。
PR #30 范围：仅 schema + APScheduler 触发；alert/regression 推 PR #31。

Revision ID: p19_w17_eval_jobs
Revises: p18_w15_message_branch
Create Date: 2026-05-23 23:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p19_w17_eval_jobs"
down_revision: Union[str, Sequence[str], None] = "p18_w15_message_branch"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eval_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("job_key", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "dataset_id",
            sa.BigInteger(),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_kind",
            sa.String(length=16),
            nullable=False,
            server_default="agent",
        ),
        sa.Column("target_key", sa.String(length=64), nullable=True),
        sa.Column("model_override", sa.String(length=64), nullable=True),
        sa.Column("prompt_override", sa.Text(), nullable=True),
        sa.Column(
            "judge",
            sa.String(length=32),
            nullable=False,
            server_default="exact_match",
        ),
        sa.Column("cron_expr", sa.String(length=64), nullable=False),
        sa.Column("alert_config", sa.JSON(), nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_score", sa.Numeric(5, 4), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "eval_job_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "job_id",
            sa.BigInteger(),
            sa.ForeignKey("eval_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dataset_run_id",
            sa.BigInteger(),
            sa.ForeignKey("dataset_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("triggered_by", sa.String(length=16), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("mean_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("delta_score", sa.Numeric(5, 4), nullable=True),
        sa.Column(
            "alert_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("alert_target", sa.String(length=256), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_eval_job_runs_job", "eval_job_runs", ["job_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_eval_job_runs_job", table_name="eval_job_runs")
    op.drop_table("eval_job_runs")
    op.drop_table("eval_jobs")
