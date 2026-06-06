"""ModelPricing service —— 按时间查价 + cost 计算 + 默认 seed"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.data.models import MediaPricing, ModelPricing
from chameleon.system.pricing.units import PricingUnit, VideoTier

#: 内置默认价目（USD per 1K tokens；2026-Q4 主流模型公开价）
#: 改这里只影响新装的库；已存在 model_pricing 行不会被覆盖（seed_if_empty）
DEFAULT_PRICING: list[tuple[str, float, float]] = [
    # (model_code, prompt_per_1k, completion_per_1k)
    ("gpt-4o", 0.0025, 0.010),
    ("gpt-4o-mini", 0.00015, 0.0006),
    ("gpt-4-turbo", 0.010, 0.030),
    ("gpt-3.5-turbo", 0.0005, 0.0015),
    ("claude-opus-4", 0.015, 0.075),
    ("claude-sonnet-4", 0.003, 0.015),
    ("claude-haiku-4", 0.0008, 0.004),
    ("qwen-plus", 0.000114, 0.000343),
    ("qwen-turbo", 0.0000428, 0.000114),
    ("qwen-max", 0.000286, 0.000857),
    ("deepseek-chat", 0.00014, 0.00028),
    # embedding（仅输入计费，completion_per_1k=0）
    ("text-embedding-3-small", 0.00002, 0.0),
    ("text-embedding-3-large", 0.00013, 0.0),
    ("text-embedding-ada-002", 0.0001, 0.0),
    ("text-embedding-v1", 0.0001, 0.0),
    ("text-embedding-v2", 0.0001, 0.0),
    ("text-embedding-v3", 0.00007, 0.0),
]


async def get_active_pricing(
    session: AsyncSession, model_code: str, *, at: datetime | None = None
) -> ModelPricing | None:
    """取某 model 在 at 时刻生效的价目（最新 effective_from ≤ at）"""
    when = at or datetime.now(timezone.utc)
    row = (
        await session.execute(
            select(ModelPricing)
            .where(
                ModelPricing.model_code == model_code,
                ModelPricing.effective_from <= when,
            )
            .order_by(ModelPricing.effective_from.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


async def calc_cost(
    session: AsyncSession,
    *,
    model_code: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    at: datetime | None = None,
) -> Decimal | None:
    """按当时价目计算原始模型成本；价目缺失返 None（call_log 仍写 token 字段）"""
    if not model_code:
        return None
    if not prompt_tokens and not completion_tokens:
        return None
    pricing = await get_active_pricing(session, model_code, at=at)
    if pricing is None:
        return None
    p = Decimal(prompt_tokens or 0) * pricing.prompt_price_per_1k / Decimal(1000)
    c = (
        Decimal(completion_tokens or 0)
        * pricing.completion_price_per_1k
        / Decimal(1000)
    )
    return (p + c).quantize(Decimal("0.000001"))


#: 内置媒体价目（CNY 元；qwen/万相公开价）。(model_code, unit, tier, price)
#: image：tier="" 无档；video_second：tier=分辨率。改这里只影响新装库（不覆盖已存在）
DEFAULT_MEDIA_PRICING: list[tuple[str, str, str, float]] = [
    ("qwen-image", PricingUnit.IMAGE, "", 0.2),
    ("qwen-image-plus", PricingUnit.IMAGE, "", 0.2),
    ("qwen-image-2.0", PricingUnit.IMAGE, "", 0.2),
    ("qwen-image-2.0-pro", PricingUnit.IMAGE, "", 0.5),
    ("wan2.7-i2v", PricingUnit.VIDEO_SECOND, VideoTier.P720, 0.6),
    ("wan2.7-i2v", PricingUnit.VIDEO_SECOND, VideoTier.P1080, 1.0),
]


async def get_active_media_pricing(
    session: AsyncSession,
    model_code: str,
    *,
    unit: str,
    tier: str = "",
    at: datetime | None = None,
) -> MediaPricing | None:
    """取某 (model, unit, tier) 在 at 时刻生效的媒体价目。"""
    when = at or datetime.now(timezone.utc)
    return (
        await session.execute(
            select(MediaPricing)
            .where(
                MediaPricing.model_code == model_code,
                MediaPricing.unit == unit,
                MediaPricing.tier == (tier or ""),
                MediaPricing.effective_from <= when,
            )
            .order_by(MediaPricing.effective_from.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def calc_media_cost(
    session: AsyncSession,
    *,
    model_code: str | None,
    unit: str,
    quantity: float,
    tier: str = "",
    at: datetime | None = None,
) -> Decimal | None:
    """按当时价目算媒体成本（CNY）。quantity：图=张数，视频=秒数。价目缺失返 None。"""
    if not model_code or not quantity:
        return None
    pricing = await get_active_media_pricing(
        session, model_code, unit=unit, tier=tier, at=at
    )
    if pricing is None:
        return None
    return (pricing.price * Decimal(str(quantity))).quantize(Decimal("0.000001"))


async def seed_media_pricing(session: AsyncSession) -> int:
    """启动期 seed 内置媒体价目（已存在 (model,unit,tier) 则跳过）。"""
    existing = {
        (c, u, t)
        for c, u, t in (
            await session.execute(
                select(
                    MediaPricing.model_code, MediaPricing.unit, MediaPricing.tier
                ).distinct()
            )
        ).all()
    }
    now = datetime.now(timezone.utc)
    added = 0
    for code, unit, tier, price in DEFAULT_MEDIA_PRICING:
        if (code, str(unit), tier) in existing:
            continue
        session.add(
            MediaPricing(
                model_code=code,
                unit=str(unit),
                tier=tier,
                price=Decimal(str(price)),
                currency="CNY",
                effective_from=now,
            )
        )
        added += 1
    if added:
        await session.commit()
        logger.info("media_pricing seeded | count={}", added)
    return added


async def seed_default_pricing(session: AsyncSession) -> int:
    """启动期 seed 内置价目（已存在则跳过；不覆盖 admin 改过的）

    Returns:
        新插入的行数
    """
    existing = (
        (
            await session.execute(
                select(ModelPricing.model_code).distinct()
            )
        )
        .scalars()
        .all()
    )
    existing_set = set(existing)
    now = datetime.now(timezone.utc)
    added = 0
    for code, prompt_price, completion_price in DEFAULT_PRICING:
        if code in existing_set:
            continue
        session.add(
            ModelPricing(
                model_code=code,
                effective_from=now,
                prompt_price_per_1k=Decimal(str(prompt_price)),
                completion_price_per_1k=Decimal(str(completion_price)),
            )
        )
        added += 1
    if added:
        await session.commit()
        logger.info("model_pricing seeded | count={}", added)
    return added
