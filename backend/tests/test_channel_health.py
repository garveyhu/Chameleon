"""P23.C6: channel 健康维护 —— fail_count 半衰 + auto_disabled 冷却恢复

decay_and_recover_channels 是纯 DB 逻辑，直接造 channel 行验证：
- ENABLED + 失败已久 → fail_count 半衰；新近失败不衰减
- AUTO_DISABLED + 冷却到期 → 重新 ENABLED + fail_count 归 0；未到期不动
- MANUAL_DISABLED 不被自动恢复
- 连续失败 disable（mark_failed 阈值）仍生效
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.jobs import decay_and_recover_channels
from chameleon.core.models import Channel, Provider
from chameleon.core.models.channel import ChannelStatus
from chameleon.core.routing.router import mark_failed


@pytest_asyncio.fixture
async def provider_id():
    pid_holder: dict = {}
    async with AsyncSessionLocal() as s:
        p = Provider(code=f"ch-prov-{secrets.token_hex(3)}", kind="llm", name="ch")
        s.add(p)
        await s.flush()
        pid_holder["id"] = p.id
        await s.commit()
    yield pid_holder["id"]
    async with AsyncSessionLocal() as s:
        await s.execute(
            delete(Channel).where(Channel.provider_id == pid_holder["id"])
        )
        await s.execute(delete(Provider).where(Provider.id == pid_holder["id"]))
        await s.commit()


async def _mk_channel(
    pid: int, *, status: str, fail_count: int, failed_minutes_ago: int | None
) -> int:
    now = datetime.now(timezone.utc)
    last_failed = (
        now - timedelta(minutes=failed_minutes_ago)
        if failed_minutes_ago is not None
        else None
    )
    async with AsyncSessionLocal() as s:
        ch = Channel(
            provider_id=pid,
            name=f"ch-{secrets.token_hex(2)}",
            status=status,
            fail_count=fail_count,
            last_failed_at=last_failed,
        )
        s.add(ch)
        await s.flush()
        cid = ch.id
        await s.commit()
    return cid


async def _get(cid: int) -> Channel:
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(select(Channel).where(Channel.id == cid))
        ).scalar_one()


async def test_decay_halves_stale_fail_count(provider_id: int):
    cid = await _mk_channel(
        provider_id,
        status=ChannelStatus.ENABLED.value,
        fail_count=4,
        failed_minutes_ago=10,
    )
    async with AsyncSessionLocal() as s:
        res = await decay_and_recover_channels(s)
    assert res["decayed"] >= 1
    assert (await _get(cid)).fail_count == 2  # 4 // 2


async def test_decay_skips_recent_failure(provider_id: int):
    cid = await _mk_channel(
        provider_id,
        status=ChannelStatus.ENABLED.value,
        fail_count=4,
        failed_minutes_ago=1,  # 1min 前刚失败 < 5min 窗口
    )
    async with AsyncSessionLocal() as s:
        await decay_and_recover_channels(s)
    assert (await _get(cid)).fail_count == 4  # 不衰减


async def test_recover_reenables_after_cooldown(provider_id: int):
    cid = await _mk_channel(
        provider_id,
        status=ChannelStatus.AUTO_DISABLED.value,
        fail_count=5,
        failed_minutes_ago=10,
    )
    async with AsyncSessionLocal() as s:
        res = await decay_and_recover_channels(s)
    assert res["recovered"] >= 1
    ch = await _get(cid)
    assert ch.status == ChannelStatus.ENABLED.value
    assert ch.fail_count == 0


async def test_recover_skips_within_cooldown(provider_id: int):
    cid = await _mk_channel(
        provider_id,
        status=ChannelStatus.AUTO_DISABLED.value,
        fail_count=5,
        failed_minutes_ago=2,  # 2min < 5min 冷却
    )
    async with AsyncSessionLocal() as s:
        await decay_and_recover_channels(s)
    assert (await _get(cid)).status == ChannelStatus.AUTO_DISABLED.value


async def test_manual_disabled_not_recovered(provider_id: int):
    cid = await _mk_channel(
        provider_id,
        status=ChannelStatus.MANUAL_DISABLED.value,
        fail_count=5,
        failed_minutes_ago=60,
    )
    async with AsyncSessionLocal() as s:
        await decay_and_recover_channels(s)
    # 管理员手停的不自动恢复
    assert (await _get(cid)).status == ChannelStatus.MANUAL_DISABLED.value


async def test_continuous_failures_auto_disable(provider_id: int):
    """连续失败到阈值 → mark_failed 自动 disable（实时路径兜底）"""
    cid = await _mk_channel(
        provider_id,
        status=ChannelStatus.ENABLED.value,
        fail_count=0,
        failed_minutes_ago=None,
    )
    async with AsyncSessionLocal() as s:
        for _ in range(5):
            await mark_failed(s, cid, auto_disable_threshold=5)
        await s.commit()
    ch = await _get(cid)
    assert ch.fail_count == 5
    assert ch.status == ChannelStatus.AUTO_DISABLED.value
