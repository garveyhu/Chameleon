"""ModelPricing service —— 按时间查价 + cost 计算 + 默认 seed"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.data.models import ModelPricing

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
