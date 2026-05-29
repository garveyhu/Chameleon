"""EvalJob ORM —— P19.1 Eval 自动化

业务概念：
- EvalJob：把 (dataset_id, target, judge) 打包成一个可周期触发的任务，描述"每天/每周拿这批样本跑一遍"
- EvalJobRun：一次实际触发；持 dataset_run_id 指向具体跑结果

PR #30 范围：仅 schema + APScheduler 触发。Alert / regression 推 PR #31。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.data.models.base import Base, TimestampMixin, snowflake_pk


class EvalJob(Base, TimestampMixin):
    """周期触发的 Eval 任务定义"""

    __tablename__ = "eval_jobs"

    id: Mapped[int] = snowflake_pk()
    job_key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    dataset_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    # graph | agent —— 当前 PR #30 只用 invoke 模式（同 datasets.runner），target_kind/key 保留扩展位
    target_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="agent"
    )
    target_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # model / prompt 透传给 runner
    model_override: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    prompt_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge: Mapped[str] = mapped_column(
        String(32), nullable=False, default="exact_match"
    )
    # P21.2：可选 EvalTemplate 绑定（freeze 当前 version，老 job 不受 template 改动影响）
    template_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("eval_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    template_version_frozen: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    cron_expr: Mapped[str] = mapped_column(String(64), nullable=False)
    # PR #31 用：{ kind: slack|webhook, target, regression_threshold }
    alert_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )


class EvalJobRun(Base):
    """单次 EvalJob 触发记录 —— 串 dataset_run_id 指向具体结果"""

    __tablename__ = "eval_job_runs"

    id: Mapped[int] = snowflake_pk()
    job_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("eval_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    dataset_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("dataset_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    # cron / manual / api
    triggered_by: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    mean_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    # 相比上次的 score 变化；PR #31 alert 用
    delta_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    alert_sent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    alert_target: Mapped[str | None] = mapped_column(
        String(256), nullable=True
    )
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_eval_job_runs_job", "job_id", "created_at"),
    )
