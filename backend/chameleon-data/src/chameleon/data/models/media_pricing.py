"""MediaPricing ORM —— 媒体生成价目（按张 / 按秒，支持分辨率分档）。

与 ModelPricing（token 计费）平行：媒体生成无 token，按 unit + tier 计价。
- unit=image：按张，tier=None，price=每张价
- unit=video_second：按秒，tier=分辨率(如 720P/1080P)，price=每秒价

设计为高可扩展：新单位 / 新分辨率 = 新增行，无需迁移。按 (model_code, unit,
tier, effective_from) 历史归档，call_log 写入时取当时生效价并存死（cost 可重放）。
币种统一 CNY（元）。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.data.models.base import Base, snowflake_pk


class MediaPricing(Base):
    """媒体生成价目（按时间版本 + 分辨率分档）"""

    __tablename__ = "media_pricing"

    id: Mapped[int] = snowflake_pk()
    model_code: Mapped[str] = mapped_column(String(64), nullable=False)
    # PricingUnit：image / video_second（见 system.pricing.units）
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    # 分辨率等分档键（video 用 720P/1080P；image 无档为空串，便于唯一约束）
    tier: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="", default=""
    )
    # 单价（CNY 元）：每张 / 每秒
    price: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="CNY", default="CNY"
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "model_code",
            "unit",
            "tier",
            "effective_from",
            name="uq_media_pricing_code_unit_tier_ts",
        ),
    )
