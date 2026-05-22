"""chameleon.core.routing.router 单测

用真实 PG（同 e2e fixture）插入测试数据，覆盖：
- 单 channel 简单解析
- 多 channel 同 priority 加权随机分布
- 不同 priority 取最高
- enabled=False 跳过
- channel.status 非 enabled 跳过
- exclude_channels 排除（failover）
- group_id 精确匹配优先于 NULL 全局
- 没匹配抛 NoSatisfiedChannelError
- mark_success / mark_failed 写入 + auto_disable 阈值
"""

from __future__ import annotations

import secrets
from collections import Counter

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import Ability, Channel, Provider
from chameleon.core.models.channel import ChannelStatus
from chameleon.core.routing import (
    NoSatisfiedChannelError,
    mark_failed,
    mark_success,
    resolve_channel,
)


@pytest_asyncio.fixture
async def fixture_data():
    """临时插入 1 provider + 多 channel + 多 ability；测试完清理"""
    suffix = secrets.token_hex(3)
    model_code = f"test-model-{suffix}"

    async with AsyncSessionLocal() as s:
        provider = Provider(
            code=f"router-prov-{suffix}",
            kind="llm",
            name="Router Test Provider",
            enabled=True,
        )
        s.add(provider)
        await s.flush()

        ch_a = Channel(
            provider_id=provider.id, name="A", status=ChannelStatus.ENABLED.value
        )
        ch_b = Channel(
            provider_id=provider.id, name="B", status=ChannelStatus.ENABLED.value
        )
        ch_c = Channel(
            provider_id=provider.id, name="C", status=ChannelStatus.ENABLED.value
        )
        s.add_all([ch_a, ch_b, ch_c])
        await s.flush()
        await s.commit()

        ch_ids = (ch_a.id, ch_b.id, ch_c.id)
        provider_id = provider.id

    yield {"model_code": model_code, "channel_ids": ch_ids, "provider_id": provider_id}

    # 清理
    async with AsyncSessionLocal() as s:
        await s.execute(
            delete(Ability).where(Ability.channel_id.in_(ch_ids))
        )
        await s.execute(delete(Channel).where(Channel.id.in_(ch_ids)))
        await s.execute(delete(Provider).where(Provider.id == provider_id))
        await s.commit()


async def _add_ability(
    model_code: str,
    channel_id: int,
    *,
    group_id: int | None = None,
    priority: int = 0,
    weight: int = 0,
    enabled: bool = True,
) -> int:
    """快速插一条 ability"""
    async with AsyncSessionLocal() as s:
        a = Ability(
            group_id=group_id,
            model_code=model_code,
            channel_id=channel_id,
            priority=priority,
            weight=weight,
            enabled=enabled,
        )
        s.add(a)
        await s.flush()
        await s.commit()
        return a.id


async def _set_channel_status(channel_id: int, status: str) -> None:
    async with AsyncSessionLocal() as s:
        ch = (
            await s.execute(select(Channel).where(Channel.id == channel_id))
        ).scalar_one()
        ch.status = status
        await s.commit()


# ── 基本解析 ──────────────────────────────────────────────


async def test_resolve_single_channel(fixture_data):
    mc = fixture_data["model_code"]
    ch_a, ch_b, ch_c = fixture_data["channel_ids"]
    await _add_ability(mc, ch_a)
    async with AsyncSessionLocal() as s:
        ch = await resolve_channel(s, model_code=mc)
        assert ch.id == ch_a


async def test_resolve_picks_highest_priority(fixture_data):
    mc = fixture_data["model_code"]
    ch_a, ch_b, _ = fixture_data["channel_ids"]
    await _add_ability(mc, ch_a, priority=0)
    await _add_ability(mc, ch_b, priority=10)  # 更高优先级
    async with AsyncSessionLocal() as s:
        ch = await resolve_channel(s, model_code=mc)
        assert ch.id == ch_b  # 高优先级胜


async def test_resolve_weighted_random_distribution(fixture_data):
    mc = fixture_data["model_code"]
    ch_a, ch_b, _ = fixture_data["channel_ids"]
    await _add_ability(mc, ch_a, weight=1)
    await _add_ability(mc, ch_b, weight=9)  # 9 倍权重

    counter: Counter = Counter()
    async with AsyncSessionLocal() as s:
        for _ in range(200):
            ch = await resolve_channel(s, model_code=mc)
            counter[ch.id] += 1
    # B 应明显多于 A（理论 9:1，给宽松一点 5:1 以上即可）
    assert counter[ch_b] > counter[ch_a] * 3, (
        f"weighted distribution off: {dict(counter)}"
    )


async def test_resolve_equal_weight_etc(fixture_data):
    """同 priority、weight=0 → 等权随机"""
    mc = fixture_data["model_code"]
    ch_a, ch_b, _ = fixture_data["channel_ids"]
    await _add_ability(mc, ch_a)
    await _add_ability(mc, ch_b)
    counter: Counter = Counter()
    async with AsyncSessionLocal() as s:
        for _ in range(60):
            ch = await resolve_channel(s, model_code=mc)
            counter[ch.id] += 1
    assert counter[ch_a] > 5 and counter[ch_b] > 5


# ── 过滤行为 ──────────────────────────────────────────────


async def test_ability_disabled_skipped(fixture_data):
    mc = fixture_data["model_code"]
    ch_a, ch_b, _ = fixture_data["channel_ids"]
    await _add_ability(mc, ch_a, enabled=False)
    await _add_ability(mc, ch_b, enabled=True)
    async with AsyncSessionLocal() as s:
        ch = await resolve_channel(s, model_code=mc)
        assert ch.id == ch_b


async def test_channel_auto_disabled_skipped(fixture_data):
    mc = fixture_data["model_code"]
    ch_a, ch_b, _ = fixture_data["channel_ids"]
    await _add_ability(mc, ch_a)
    await _add_ability(mc, ch_b)
    # A 被自动停用
    await _set_channel_status(ch_a, ChannelStatus.AUTO_DISABLED.value)
    async with AsyncSessionLocal() as s:
        for _ in range(20):
            ch = await resolve_channel(s, model_code=mc)
            assert ch.id == ch_b


async def test_exclude_channels(fixture_data):
    mc = fixture_data["model_code"]
    ch_a, ch_b, _ = fixture_data["channel_ids"]
    await _add_ability(mc, ch_a, priority=10)
    await _add_ability(mc, ch_b, priority=10)
    async with AsyncSessionLocal() as s:
        ch = await resolve_channel(
            s, model_code=mc, exclude_channels={ch_a}
        )
        assert ch.id == ch_b


async def test_no_satisfied_raises(fixture_data):
    mc = fixture_data["model_code"]
    # 没插任何 ability
    async with AsyncSessionLocal() as s:
        with pytest.raises(NoSatisfiedChannelError):
            await resolve_channel(s, model_code=mc)


async def test_no_satisfied_after_exclude_all(fixture_data):
    mc = fixture_data["model_code"]
    ch_a, _, _ = fixture_data["channel_ids"]
    await _add_ability(mc, ch_a)
    async with AsyncSessionLocal() as s:
        with pytest.raises(NoSatisfiedChannelError):
            await resolve_channel(
                s, model_code=mc, exclude_channels={ch_a}
            )


# ── group_id 作用域 ───────────────────────────────────────


async def test_group_specific_takes_priority(fixture_data):
    """精确 group_id 比全局优先"""
    mc = fixture_data["model_code"]
    ch_a, ch_b, _ = fixture_data["channel_ids"]
    await _add_ability(mc, ch_a, group_id=None, priority=10)  # 全局高优先
    await _add_ability(mc, ch_b, group_id=42, priority=0)  # 精确 group 低优先
    async with AsyncSessionLocal() as s:
        # group=42 应路由到 B（虽然 B priority 更低，但精确 group 先匹配）
        ch = await resolve_channel(s, model_code=mc, group_id=42)
        assert ch.id == ch_b


async def test_group_fallback_to_global(fixture_data):
    """精确 group_id 没匹配时 fallback NULL 全局"""
    mc = fixture_data["model_code"]
    ch_a, _, _ = fixture_data["channel_ids"]
    await _add_ability(mc, ch_a, group_id=None)
    async with AsyncSessionLocal() as s:
        ch = await resolve_channel(s, model_code=mc, group_id=999)
        assert ch.id == ch_a


# ── 健康监控 ──────────────────────────────────────────────


async def test_mark_success_resets_fail_count(fixture_data):
    ch_a, _, _ = fixture_data["channel_ids"]
    async with AsyncSessionLocal() as s:
        ch = (await s.execute(select(Channel).where(Channel.id == ch_a))).scalar_one()
        ch.fail_count = 3
        await s.commit()

    async with AsyncSessionLocal() as s:
        await mark_success(s, ch_a, elapsed_ms=120)
        await s.commit()

    async with AsyncSessionLocal() as s:
        ch = (await s.execute(select(Channel).where(Channel.id == ch_a))).scalar_one()
        assert ch.fail_count == 0
        assert ch.last_success_at is not None
        assert ch.response_time_ms == 120


async def test_mark_success_ewma_response_time(fixture_data):
    ch_a, _, _ = fixture_data["channel_ids"]
    async with AsyncSessionLocal() as s:
        ch = (await s.execute(select(Channel).where(Channel.id == ch_a))).scalar_one()
        ch.response_time_ms = 100
        await s.commit()
    async with AsyncSessionLocal() as s:
        await mark_success(s, ch_a, elapsed_ms=200)  # 新值 200
        await s.commit()
    async with AsyncSessionLocal() as s:
        ch = (await s.execute(select(Channel).where(Channel.id == ch_a))).scalar_one()
        # 100 * 0.7 + 200 * 0.3 = 70 + 60 = 130
        assert ch.response_time_ms == 130


async def test_mark_failed_increments_and_auto_disables(fixture_data):
    ch_a, _, _ = fixture_data["channel_ids"]
    # 阈值 3，连续 3 次失败应自动停
    async with AsyncSessionLocal() as s:
        for _ in range(3):
            await mark_failed(s, ch_a, auto_disable_threshold=3)
        await s.commit()
    async with AsyncSessionLocal() as s:
        ch = (await s.execute(select(Channel).where(Channel.id == ch_a))).scalar_one()
        assert ch.fail_count == 3
        assert ch.status == ChannelStatus.AUTO_DISABLED.value
        assert ch.last_failed_at is not None


async def test_mark_unknown_channel_silent(fixture_data):
    """未知 channel id 不应炸（best-effort）"""
    async with AsyncSessionLocal() as s:
        await mark_failed(s, 999999999999)
        await mark_success(s, 999999999999)
        # 不抛
