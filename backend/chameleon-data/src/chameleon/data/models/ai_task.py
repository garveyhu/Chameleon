"""AiTask ORM —— 系统内各种 AI 任务的统一存储。

设计（配合 chameleon-aikit 执行层）：
- aikit = 执行层（LLMRunner 跑 LLM + trace 记账）；ai_tasks = 编排/持久化/缓存层
  （异步调度 + 存状态/结果 + 同输入缓存去重）。
- task_type 对齐 aikit registry key（如 eval.compare_analysis）。
- input_hash = sha256(task_type + 规范化 input)：同输入命中已 success 的任务直接复用，
  避免重复烧 token。评测 run 是不可变快照，故「对比分析」等场景缓存天然安全。
- 进程内 asyncio 后台执行：status 由 pending→running→success/failed；进程重启时启动钩子
  把残留 running 标 failed 兜底。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.data.models.base import Base, snowflake_pk


class AiTask(Base):
    """一条 AI 任务（异步执行 + 状态跟踪 + 结果缓存）。"""

    __tablename__ = "ai_tasks"

    id: Mapped[int] = snowflake_pk()
    # 任务类型（对齐 aikit registry key，如 eval.compare_analysis）
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # 业务归属：scope=业务域（如 run_compare），scope_ref=关联实体（如 sorted run_ids）
    scope: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 缓存键：sha256(task_type + 规范化 input)；命中已 success 任务即复用
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # pending / running / success / failed / cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 执行用量（可空；aikit 调用自身另记 call_log）
    model_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_ai_tasks_input_hash", "input_hash"),
        Index("ix_ai_tasks_scope", "scope", "scope_ref"),
    )
