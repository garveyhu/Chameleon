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

from sqlalchemy import (
    JSON,
    BigInteger,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, TimestampMixin, snowflake_pk


class Dataset(Base, TimestampMixin):
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
