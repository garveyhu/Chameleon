"""ModelPricing ORM —— P22.1 PR #71

业务：模型价目表，按 (model_code, effective_from) 历史归档。call_log 写入时
用当时生效的价目计算 cost_usd 并存死；后续改价目不溯源（红线：cost 可重放）。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, snowflake_pk


class ModelPricing(Base):
    """模型价目（按时间版本）"""

    __tablename__ = "model_pricing"

    id: Mapped[int] = snowflake_pk()
    model_code: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # 单位价格 ÷ 1000 tokens（与各家厂商定价单位对齐）
    prompt_price_per_1k: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False
    )
    completion_price_per_1k: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False
    )
    currency: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="USD", default="USD"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "model_code", "effective_from", name="uq_model_pricing_code_ts"
        ),
    )
