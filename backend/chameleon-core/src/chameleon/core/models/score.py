"""Score ORM —— call_log 上的"评分 / 反馈"事件

设计参考 LangFuse Scores：
一个 trace 或 observation 上可挂任意条 Score，名字 + 类型自由组合。
典型场景：
- 用户在 widget 点 "👍"  → name='thumbs_up', value=1, source='feedback'
- LLM-as-judge 跑评估 → name='ragas_faithfulness', value=0.83, source='eval'
- 标注员人工打分 → name='helpful', value=4, source='annotation'

写多读少 → 不带 updated_at，append-only。
关联键不强约束（不建 FK），call_log 软删时 score 行保留作历史快照。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, snowflake_pk


class Score(Base):
    """call_log（trace 根或子 observation）上的评分事件"""

    __tablename__ = "scores"

    id: Mapped[int] = snowflake_pk()
    # 指向 call_logs.request_id（不是 PK，便于跨 trace 聚合）
    call_log_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 冗余存 trace 根 id（用于跨子 observation 聚合）
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 评分名称（"thumbs_up" / "user_rating" / "ragas_faithfulness"）
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # 数值评分（thumbs=1/-1，rating=1..5，质量=0..1）
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 文本 / 类别评分（如 'positive'/'negative'）
    string_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    # numeric / categorical / boolean / text
    data_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # annotation / api / eval / feedback
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="api"
    )
    # 用户附言（widget 反馈输入框）
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_scores_call", "call_log_id"),
        Index("ix_scores_trace_name", "trace_id", "name"),
    )
