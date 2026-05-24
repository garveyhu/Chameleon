"""P23.C5: 计费分组倍率 group_ratio

覆盖：
- get_group_ratio：default/trial/vip/internal + 缺失 → 1.0
- calc_cost(group_ratio=2.0) == 2× base（trial）；默认不含倍率（红线）
- group_ratio_for_app：app → workspace 分组倍率 join
- record_call：cost_usd 存原始成本，group_ratio 单独存死
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import (
    App,
    CallLog,
    ModelPricing,
    Workspace,
)
from chameleon.system.api_key.service import record_call
from chameleon.system.pricing import (
    calc_cost,
    get_group_ratio,
    group_ratio_for_app,
)
from chameleon.system.pricing.service import get_active_pricing


@pytest_asyncio.fixture
async def trial_app():
    """trial 分组的 workspace + app + 一条价目"""
    suffix = secrets.token_hex(3)
    wid = secrets.randbelow(2_000_000_000) + 1_000_000_000
    app_key = f"gr-app-{suffix}"
    model_code = f"gr-model-{suffix}"
    async with AsyncSessionLocal() as s:
        s.add(
            Workspace(
                id=wid,
                workspace_key=f"gr-ws-{suffix}",
                name="trial ws",
                group_code="trial",
            )
        )
        await s.flush()
        s.add(App(app_key=app_key, name="gr app", workspace_id=wid))
        # 价目：prompt 1.0/1k，completion 2.0/1k（便于心算）
        s.add(
            ModelPricing(
                model_code=model_code,
                effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
                prompt_price_per_1k=Decimal("1.0"),
                completion_price_per_1k=Decimal("2.0"),
            )
        )
        await s.commit()
    yield {"ws_id": wid, "app_key": app_key, "model_code": model_code}
    async with AsyncSessionLocal() as s:
        await s.execute(delete(CallLog).where(CallLog.app_id == app_key))
        await s.execute(delete(App).where(App.app_key == app_key))
        await s.execute(delete(Workspace).where(Workspace.id == wid))
        await s.execute(
            delete(ModelPricing).where(ModelPricing.model_code == model_code)
        )
        await s.commit()


async def test_get_group_ratio_seeded():
    async with AsyncSessionLocal() as s:
        assert await get_group_ratio(s, "default") == Decimal("1.000")
        assert await get_group_ratio(s, "trial") == Decimal("2.000")
        assert await get_group_ratio(s, "vip") == Decimal("0.500")
        assert await get_group_ratio(s, "internal") == Decimal("0.000")
        # 缺失 / 空 → 1.0
        assert await get_group_ratio(s, "no-such-group") == Decimal("1.0")
        assert await get_group_ratio(s, None) == Decimal("1.0")


async def test_calc_cost_applies_group_ratio(trial_app: dict):
    """1000 prompt × 1.0/1k + 500 completion × 2.0/1k = 1.0 + 1.0 = 2.0 base
    trial ×2.0 → 4.0
    """
    async with AsyncSessionLocal() as s:
        base = await calc_cost(
            s,
            model_code=trial_app["model_code"],
            prompt_tokens=1000,
            completion_tokens=500,
        )
        effective = await calc_cost(
            s,
            model_code=trial_app["model_code"],
            prompt_tokens=1000,
            completion_tokens=500,
            group_ratio=Decimal("2.0"),
        )
    assert base == Decimal("2.000000")
    assert effective == Decimal("4.000000")  # trial ×2.0


async def test_group_ratio_for_app(trial_app: dict):
    async with AsyncSessionLocal() as s:
        ratio = await group_ratio_for_app(s, trial_app["app_key"])
    assert ratio == Decimal("2.000")


async def test_group_ratio_for_unknown_app_defaults():
    async with AsyncSessionLocal() as s:
        assert await group_ratio_for_app(s, "no-such-app") == Decimal("1.0")


async def test_record_call_stores_raw_cost_and_ratio(trial_app: dict):
    """红线：cost_usd 存原始成本（不含倍率）；group_ratio 单独存死"""
    rid = f"gr-rid-{secrets.token_hex(3)}"
    async with AsyncSessionLocal() as s:
        await record_call(
            s,
            request_id=rid,
            app_id=trial_app["app_key"],
            agent_key="example",
            session_id=None,
            stream=False,
            success=True,
            code=200,
            error_message=None,
            duration_ms=100,
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            model_code=trial_app["model_code"],
        )
        await s.commit()

    async with AsyncSessionLocal() as s:
        row = (
            await s.execute(select(CallLog).where(CallLog.request_id == rid))
        ).scalar_one()
    # cost_usd = 原始成本 2.0（不乘 trial 2.0）
    assert row.cost_usd == Decimal("2.000000")
    # group_ratio 单独存 = 2.0；effective = cost_usd × group_ratio = 4.0
    assert row.group_ratio == Decimal("2.000")


async def test_active_pricing_lookup(trial_app: dict):
    """sanity：价目按时间查得到（兜底防 fixture 漂移）"""
    async with AsyncSessionLocal() as s:
        p = await get_active_pricing(s, trial_app["model_code"])
    assert p is not None
    assert p.prompt_price_per_1k == Decimal("1.0")
