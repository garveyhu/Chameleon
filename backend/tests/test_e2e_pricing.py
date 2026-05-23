"""P22.1 PR #71 E2E：model_pricing + cost 计算 + seed"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import ModelPricing
from chameleon.system.pricing import (
    calc_cost,
    get_active_pricing,
    seed_default_pricing,
)


@pytest_asyncio.fixture
async def clean_pricing():
    """每个测试前后清空 model_pricing 避免污染"""
    async with AsyncSessionLocal() as s:
        await s.execute(delete(ModelPricing))
        await s.commit()
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(delete(ModelPricing))
        await s.commit()


# ── seed ───────────────────────────────────────────────


async def test_seed_default_pricing_inserts_builtin(clean_pricing):
    async with AsyncSessionLocal() as s:
        added = await seed_default_pricing(s)
        assert added > 5  # 至少 5 个 builtin model
        codes = (
            (await s.execute(select(ModelPricing.model_code).distinct()))
            .scalars()
            .all()
        )
        assert "gpt-4o" in codes
        assert "qwen-plus" in codes


async def test_seed_is_idempotent(clean_pricing):
    async with AsyncSessionLocal() as s:
        await seed_default_pricing(s)
        added_second = await seed_default_pricing(s)
        assert added_second == 0


# ── get_active_pricing ────────────────────────────────


async def test_get_active_pricing_latest_version(clean_pricing):
    """同 model 多 version → 取 ≤ now 的最新"""
    async with AsyncSessionLocal() as s:
        old = ModelPricing(
            model_code="test-model",
            effective_from=datetime.now(timezone.utc) - timedelta(days=30),
            prompt_price_per_1k=Decimal("0.001"),
            completion_price_per_1k=Decimal("0.002"),
        )
        new = ModelPricing(
            model_code="test-model",
            effective_from=datetime.now(timezone.utc) - timedelta(days=1),
            prompt_price_per_1k=Decimal("0.0005"),
            completion_price_per_1k=Decimal("0.0010"),
        )
        s.add_all([old, new])
        await s.commit()

        active = await get_active_pricing(s, "test-model")
        assert active is not None
        assert active.prompt_price_per_1k == Decimal("0.000500")


async def test_get_active_pricing_at_past_time(clean_pricing):
    """at=过去某时刻 → 取那时生效的（老版本）"""
    async with AsyncSessionLocal() as s:
        past = datetime.now(timezone.utc) - timedelta(days=15)
        s.add(
            ModelPricing(
                model_code="time-model",
                effective_from=datetime.now(timezone.utc) - timedelta(days=30),
                prompt_price_per_1k=Decimal("0.001"),
                completion_price_per_1k=Decimal("0.002"),
            )
        )
        s.add(
            ModelPricing(
                model_code="time-model",
                effective_from=datetime.now(timezone.utc) - timedelta(days=10),
                prompt_price_per_1k=Decimal("0.0005"),
                completion_price_per_1k=Decimal("0.0010"),
            )
        )
        await s.commit()

        # 15 天前应该取老版本
        old_active = await get_active_pricing(s, "time-model", at=past)
        assert old_active.prompt_price_per_1k == Decimal("0.001000")


async def test_get_active_pricing_missing_returns_none(clean_pricing):
    async with AsyncSessionLocal() as s:
        result = await get_active_pricing(s, "no-such-model")
        assert result is None


# ── calc_cost ───────────────────────────────────────


async def test_calc_cost_basic(clean_pricing):
    """gpt-4o: 0.0025/1k prompt + 0.010/1k completion；
    1000 prompt + 500 completion → 0.0025 + 0.005 = 0.0075"""
    async with AsyncSessionLocal() as s:
        await seed_default_pricing(s)
        cost = await calc_cost(
            s,
            model_code="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        assert cost == Decimal("0.007500")


async def test_calc_cost_missing_model_returns_none(clean_pricing):
    async with AsyncSessionLocal() as s:
        cost = await calc_cost(
            s,
            model_code="no-such-model",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        assert cost is None


async def test_calc_cost_zero_tokens_returns_none(clean_pricing):
    async with AsyncSessionLocal() as s:
        await seed_default_pricing(s)
        cost = await calc_cost(
            s, model_code="gpt-4o", prompt_tokens=0, completion_tokens=0
        )
        assert cost is None


async def test_calc_cost_only_prompt_tokens(clean_pricing):
    async with AsyncSessionLocal() as s:
        await seed_default_pricing(s)
        cost = await calc_cost(
            s,
            model_code="gpt-4o-mini",
            prompt_tokens=1000,
            completion_tokens=None,
        )
        # 0.00015 * 1 = 0.000150
        assert cost == Decimal("0.000150")


async def test_calc_cost_replay_uses_old_price(clean_pricing):
    """改了价目表，老 call_log 重算（at=old_time）仍用老价 ✓ 红线：cost 可重放"""
    async with AsyncSessionLocal() as s:
        past = datetime.now(timezone.utc) - timedelta(days=20)
        s.add(
            ModelPricing(
                model_code="replay-model",
                effective_from=datetime.now(timezone.utc) - timedelta(days=30),
                prompt_price_per_1k=Decimal("0.01"),
                completion_price_per_1k=Decimal("0.02"),
            )
        )
        # 新版本（5 天前生效）
        s.add(
            ModelPricing(
                model_code="replay-model",
                effective_from=datetime.now(timezone.utc) - timedelta(days=5),
                prompt_price_per_1k=Decimal("0.001"),
                completion_price_per_1k=Decimal("0.002"),
            )
        )
        await s.commit()

        # 用 past 时刻算：用老价 0.01/0.02
        cost = await calc_cost(
            s,
            model_code="replay-model",
            prompt_tokens=1000,
            completion_tokens=500,
            at=past,
        )
        # 0.01 + 0.01 = 0.02
        assert cost == Decimal("0.020000")
