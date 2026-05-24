"""P23.C3: 配额预扣 pre_consume + 信任阈值 + Lua 原子 + SQL 兜底

用真实 Redis（项目既有测试约定）+ 随机 workspace_id 隔离，用例后清 key。
SQL 兜底用 stub redis（.eval 抛 RedisError）+ 真实 WorkspaceQuota 行验证。
"""

from __future__ import annotations

import secrets

import pytest
import pytest_asyncio
from redis.exceptions import RedisError
from sqlalchemy import delete

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.infra import redis as redis_infra
from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import Workspace, WorkspaceQuota
from chameleon.core.observe import billing
from chameleon.core.observe.billing import (
    PreConsumeAction,
    pre_consume,
    release_reservation,
)


@pytest_asyncio.fixture
async def ws_id():
    """随机 workspace_id；用例后清 reserved key"""
    wid = secrets.randbelow(2_000_000_000) + 1_000_000_000
    yield wid
    await redis_infra.get_redis().delete(billing.reserved_key(wid))
    async with AsyncSessionLocal() as s:
        await s.execute(
            delete(WorkspaceQuota).where(WorkspaceQuota.workspace_id == wid)
        )
        await s.execute(delete(Workspace).where(Workspace.id == wid))
        await s.commit()


async def _seed_quota(
    wid: int, *, limit: int | None, used: int
) -> None:
    """SQL 兜底用例前置：建 workspace + quota 行（FK 前置）"""
    async with AsyncSessionLocal() as s:
        s.add(
            Workspace(id=wid, workspace_key=f"ws-{wid}", name="pc test")
        )
        await s.flush()
        s.add(
            WorkspaceQuota(
                workspace_id=wid,
                token_quota_monthly=limit,
                token_used_current_month=used,
            )
        )
        await s.commit()


class _BoomRedis:
    """模拟 Redis 不可达：eval 抛 RedisError"""

    async def eval(self, *a, **k):
        raise RedisError("boom")


# ── 跳过预扣的几种情形 ──────────────────────────────────


async def test_unlimited_skips(ws_id: int):
    r = redis_infra.get_redis()
    async with AsyncSessionLocal() as s:
        res = await pre_consume(
            r, s, workspace_id=ws_id, estimated_tokens=500, quota_remaining=None
        )
    assert res.action == PreConsumeAction.UNLIMITED
    assert res.reserved == 0
    assert await r.get(billing.reserved_key(ws_id)) is None


async def test_zero_estimate_skips(ws_id: int):
    r = redis_infra.get_redis()
    async with AsyncSessionLocal() as s:
        res = await pre_consume(
            r, s, workspace_id=ws_id, estimated_tokens=0, quota_remaining=10000
        )
    assert res.action == PreConsumeAction.ZERO


async def test_high_quota_trusted(ws_id: int):
    """剩余额度 >> 预估（> 100×）→ 信任跳过，不写 Redis"""
    r = redis_infra.get_redis()
    async with AsyncSessionLocal() as s:
        res = await pre_consume(
            r, s, workspace_id=ws_id, estimated_tokens=100, quota_remaining=1_000_000
        )
    assert res.action == PreConsumeAction.TRUSTED
    assert res.reserved == 0
    assert await r.get(billing.reserved_key(ws_id)) is None


# ── 紧额度 → Redis 原子预扣 ─────────────────────────────


async def test_tight_quota_reserves(ws_id: int):
    """额度偏紧（< 100×）→ Redis 预扣，reserved 计数上升"""
    r = redis_infra.get_redis()
    async with AsyncSessionLocal() as s:
        res = await pre_consume(
            r, s, workspace_id=ws_id, estimated_tokens=100, quota_remaining=500
        )
    assert res.action == PreConsumeAction.RESERVED
    assert res.reserved == 100
    assert int(await r.get(billing.reserved_key(ws_id))) == 100


async def test_concurrent_reserve_rejects_over_budget(ws_id: int):
    """在途预扣累加超 budget → 第二次拒绝（并发防超发）"""
    r = redis_infra.get_redis()
    async with AsyncSessionLocal() as s:
        # budget=500，连扣 100×5=500 OK，第 6 次应拒
        for _ in range(5):
            await pre_consume(
                r, s, workspace_id=ws_id, estimated_tokens=100, quota_remaining=500
            )
        with pytest.raises(BusinessError) as ei:
            await pre_consume(
                r, s, workspace_id=ws_id, estimated_tokens=100, quota_remaining=500
            )
    assert ei.value.code == ResultCode.WorkspaceQuotaExceeded
    assert int(await r.get(billing.reserved_key(ws_id))) == 500


async def test_insufficient_for_estimate_raises(ws_id: int):
    r = redis_infra.get_redis()
    async with AsyncSessionLocal() as s:
        with pytest.raises(BusinessError) as ei:
            await pre_consume(
                r, s, workspace_id=ws_id, estimated_tokens=600, quota_remaining=500
            )
    assert ei.value.code == ResultCode.WorkspaceQuotaExceeded


async def test_release_reservation(ws_id: int):
    r = redis_infra.get_redis()
    async with AsyncSessionLocal() as s:
        await pre_consume(
            r, s, workspace_id=ws_id, estimated_tokens=300, quota_remaining=500
        )
    await release_reservation(r, workspace_id=ws_id, amount=300)
    assert int(await r.get(billing.reserved_key(ws_id))) == 0


# ── Redis 不可达 → SQL FOR UPDATE 兜底 ──────────────────


async def test_sql_fallback_allows_when_under_limit(ws_id: int):
    await _seed_quota(ws_id, limit=1000, used=200)
    async with AsyncSessionLocal() as s:
        res = await pre_consume(
            _BoomRedis(),
            s,
            workspace_id=ws_id,
            estimated_tokens=100,
            quota_remaining=500,
        )
    assert res.action == PreConsumeAction.SQL_FALLBACK
    assert res.reserved == 0


async def test_sql_fallback_rejects_when_exhausted(ws_id: int):
    await _seed_quota(ws_id, limit=1000, used=1000)
    async with AsyncSessionLocal() as s:
        with pytest.raises(BusinessError) as ei:
            await pre_consume(
                _BoomRedis(),
                s,
                workspace_id=ws_id,
                estimated_tokens=100,
                quota_remaining=500,
            )
    assert ei.value.code == ResultCode.WorkspaceQuotaExceeded
