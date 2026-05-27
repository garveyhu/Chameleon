"""EvalTemplate ORM —— P21.2 PR #62

评判模板：把 metrics 配置（[{name, algorithm, weight, threshold}]）打包复用，
绑到多个 EvalJob 上。

红线（plan §2 P21 新增）：
- ⛔ template 改动 → version 自增；老 EvalJob 引用 freeze 版本，行为不变
- ⛔ RAGAS builtin 算子不允许用户改 weight/metric definition；要 customize
  走 EvalTemplate.config 字段
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, TimestampMixin, snowflake_pk


class EvalTemplate(Base, TimestampMixin):
    """评判模板（多 metric 加权 + 阈值）"""

    __tablename__ = "eval_templates"

    id: Mapped[int] = snowflake_pk()
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # metrics: [{ name, algorithm, weight: 0.0-1.0, threshold: 0.0-1.0 | null, config?: {} }]
    metrics: Mapped[list] = mapped_column(JSON, nullable=False)
    # judge LLM 模型（如 gpt-4o-mini）；None = 走系统默认
    judge_provider: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    # 自增版本：每次 update 时 +1，老 EvalJob 引用 version_frozen 不变
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )

    __table_args__ = (
        # (name, version) 唯一；不同 version 共存以支持 freeze
        UniqueConstraint(
            "name", "version", name="uq_eval_templates_name_ver"
        ),
    )
