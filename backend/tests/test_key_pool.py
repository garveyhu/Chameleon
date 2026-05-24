"""P23.C7: 多 key 池 round-robin + 失败隔离

用真实 Redis（项目约定）+ 随机 channel_id 隔离 key，用例后清 pool/quarantine key。
"""

from __future__ import annotations

import secrets

import pytest_asyncio

from chameleon.core.infra import redis as redis_infra
from chameleon.core.models import Channel
from chameleon.core.routing import key_pool
from chameleon.core.routing.key_pool import (
    next_key_index,
    quarantine_key,
    select_channel_key,
)
from chameleon.core.utils.crypto import encrypt


@pytest_asyncio.fixture
async def cid():
    cid = secrets.randbelow(2_000_000_000) + 1_000_000_000
    yield cid
    r = redis_infra.get_redis()
    await r.delete(key_pool.pool_list_key(cid))
    await r.delete(key_pool.quarantine_set_key(cid))


async def test_round_robin_cycles_all_indices(cid: int):
    """连续取 3 次（池大小 3）应覆盖 {0,1,2}，第 4 次回到首"""
    r = redis_infra.get_redis()
    seen = [await next_key_index(r, cid, 3) for _ in range(3)]
    assert sorted(seen) == [0, 1, 2]
    # 第 4 次与第 1 次相同（环形）
    fourth = await next_key_index(r, cid, 3)
    assert fourth == seen[0]


async def test_quarantine_skipped(cid: int):
    """隔离下标 1 后，轮转不再返回 1"""
    r = redis_infra.get_redis()
    await quarantine_key(r, cid, 1)
    picks = {await next_key_index(r, cid, 3) for _ in range(6)}
    assert 1 not in picks
    assert picks == {0, 2}


async def test_all_quarantined_degrades_not_fail(cid: int):
    """整池隔离 → 仍返回一个合法下标（降级不 fail）"""
    r = redis_infra.get_redis()
    for i in range(3):
        await quarantine_key(r, cid, i)
    idx = await next_key_index(r, cid, 3)
    assert 0 <= idx < 3


async def test_select_channel_key_uses_pool(cid: int):
    """channel.keys 非空 → 轮转选池中 key（解密返明文）"""
    ch = Channel(
        id=cid,
        provider_id=1,
        name="kp",
        keys=[encrypt("KEY-A"), encrypt("KEY-B")],
    )
    r = redis_infra.get_redis()
    seen = set()
    for _ in range(4):
        idx, key = await select_channel_key(r, ch)
        assert idx in (0, 1)
        assert key in ("KEY-A", "KEY-B")
        seen.add(key)
    # 两个 key 都被轮到
    assert seen == {"KEY-A", "KEY-B"}


async def test_select_channel_key_single_fallback(cid: int):
    """channel.keys 空 → 退回单 key（key_index=None）"""
    ch = Channel(
        id=cid,
        provider_id=1,
        name="kp",
        keys=None,
        api_key_encrypted=encrypt("SOLO"),
    )
    r = redis_infra.get_redis()
    idx, key = await select_channel_key(r, ch)
    assert idx is None
    assert key == "SOLO"


async def test_quarantine_then_select_skips(cid: int):
    """隔离池中失败 key → select 不再返回它"""
    ch = Channel(
        id=cid,
        provider_id=1,
        name="kp",
        keys=[encrypt("K0"), encrypt("K1"), encrypt("K2")],
    )
    r = redis_infra.get_redis()
    await quarantine_key(r, cid, 1)  # 隔离 K1
    for _ in range(6):
        idx, key = await select_channel_key(r, ch)
        assert key != "K1"
