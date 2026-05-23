"""Dataset ORM —— P18.3 Eval 链路

Dataset 概念（LangFuse 风）：
- Dataset：一批 "(input, expected_output)" 样本的集合（话题 / 场景）
- DatasetItem：单条样本，可由 call_log 一键采样而来或人工添加
- DatasetRun：用新 prompt/model 跑整个 dataset 的一次评估（PR #25 起）

红线（plan §2 新增）：
- DatasetItem 不存原始 PII —— 采样时强制脱敏 user_input
  仅保留 hash + length + token_count；展示用 redacted 替代字段
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, TimestampMixin, snowflake_pk
from chameleon.core.models.workspace import WorkspaceScopedMixin


class Dataset(Base, TimestampMixin, WorkspaceScopedMixin):
    """一组样本（按主题 / 场景）"""

    __tablename__ = "datasets"

    id: Mapped[int] = snowflake_pk()
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 冗余：item_count 由采样 / 添加时增 / 删除时减，避免每次 count(*)
    item_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )


class DatasetItem(Base, TimestampMixin):
    """单条样本（采样 or 人工添加）"""

    __tablename__ = "dataset_items"

    id: Mapped[int] = snowflake_pk()
    dataset_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 来源 call_log.request_id（采样而来）；人工添加则为 NULL
    source_call_log_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    # 已脱敏的 input —— 推荐结构：{ "hash": "sha256:...", "length": 128, "token_count": 24 }
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    # 人工标注的预期输出（PR #25 dataset_runs 用这个对比）
    expected_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 额外元数据（标签 / 难度 / 备注）
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class DatasetRun(Base):
    """一次评估运行 —— 把 dataset 全量过新 prompt/model 跑一遍"""

    __tablename__ = "dataset_runs"

    id: Mapped[int] = snowflake_pk()
    dataset_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 采用何种 invoke：模型直调（model_name）+ system_prompt 覆盖 + judge 类型
    agent_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_override: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    prompt_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    # exact_match / contains / llm_judge
    judge: Mapped[str] = mapped_column(
        String(32), nullable=False, default="exact_match"
    )
    # 内部状态：pending / running / success / failed / cancelled
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    # 聚合摘要：{"total":N, "ok":N, "fail":N, "mean_score":0.x}
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("ix_dataset_runs_ds", "dataset_id", "created_at"),)


class DatasetRunItem(Base):
    """单 item 在某次 run 下的执行结果"""

    __tablename__ = "dataset_run_items"

    id: Mapped[int] = snowflake_pk()
    dataset_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dataset_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    dataset_item_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dataset_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 实际 invoke 结果 → 用于 judge 与 expected_output 对比
    actual_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # judge 评分（0 / 1 / 0.5 等）
    score: Mapped[float | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_dataset_run_items_run", "dataset_run_id"),
    )
