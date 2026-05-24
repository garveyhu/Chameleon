"""P23.C4: post-consume 差额返还 + 并发结算原子性

验证：
- post_consume 释放本次请求预扣（差额自然返还）
- 30 并发 pre→settle 循环后：在途预扣归 0，SQL committed token_used == sum(actual) ±1
- post_consume 幂等（重复调不会扣穿）/ 无标记时 no-op
"""

from __future__ import annotations

import asyncio
import secrets

import pytest_asyncio
from sqlalchemy import delete, select

from chameleon.core.infra import redis as redis_infra
from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import Workspace, WorkspaceQuota
from chameleon.core.observe import billing, post_consume, pre_consume
from chameleon.system.workspaces.quota_service import increment_usage


@pytest_asyncio.fixture
async def ws():
    wid = secrets.randbelow(2_000_000_000) + 1_000_000_000
    async with AsyncSessionLocal() as s:
        s.add(Workspace(id=wid, workspace_key=f"ws-{wid}", name="pc test"))
        await s.flush()
        s.add(
            WorkspaceQuota(
                workspace_id=wid,
                token_quota_monthly=10_000_000,
                token_used_current_month=0,
            )
        )
        await s.commit()
    yield wid
    await redis_infra.get_redis().delete(billing.reserved_key(wid))
    async with AsyncSessionLocal() as s:
        await s.execute(
            delete(WorkspaceQuota).where(WorkspaceQuota.workspace_id == wid)
        )
        await s.execute(delete(Workspace).where(Workspace.id == wid))
        await s.commit()


async def _committed(wid: int) -> int:
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(
                select(WorkspaceQuota.token_used_current_month).where(
                    WorkspaceQuota.workspace_id == wid
                )
            )
        ).scalar_one()


async def test_post_consume_releases_reservation(ws: int):
    r = redis_infra.get_redis()
    rid = f"rid-{secrets.token_hex(3)}"
    async with AsyncSessionLocal() as s:
        # 紧额度强制 RESERVED（quota_remaining 不超 100×est）
        await pre_consume(
            r,
            s,
            workspace_id=ws,
            estimated_tokens=100,
            quota_remaining=500,
            request_id=rid,
        )
    assert int(await r.get(billing.reserved_key(ws))) == 100

    released = await post_consume(r, workspace_id=ws, request_id=rid)
    assert released == 100
    assert int(await r.get(billing.reserved_key(ws))) == 0
    # 幂等：再调返回 0，不扣穿
    again = await post_consume(r, workspace_id=ws, request_id=rid)
    assert again == 0
    assert int(await r.get(billing.reserved_key(ws))) == 0


async def test_post_consume_no_marker_noop(ws: int):
    r = redis_infra.get_redis()
    released = await post_consume(r, workspace_id=ws, request_id="never-reserved")
    assert released == 0


async def test_30_concurrent_settle_atomic(ws: int):
    """30 并发：每个预扣 100 → 实际用量随机 → settle 释放预扣 + 落 SQL

    断言：committed token_used == sum(actual)；在途预扣归 0。
    """
    r = redis_infra.get_redis()
    actuals = [secrets.randbelow(80) + 10 for _ in range(30)]  # 10..89

    async def one(i: int, actual: int) -> None:
        rid = f"conc-{secrets.token_hex(3)}-{i}"
        async with AsyncSessionLocal() as s:
            # quota_remaining=5000：< 100×est(10000) 强制走 RESERVED，
            # 又宽于 30×100=3000 让 30 个并发预扣都能放下
            await pre_consume(
                r,
                s,
                workspace_id=ws,
                estimated_tokens=100,
                quota_remaining=5000,
                request_id=rid,
            )
            await s.commit()
        async with AsyncSessionLocal() as s:
            await increment_usage(s, ws, total_tokens=actual, requests=1)
            await s.commit()
        await post_consume(r, workspace_id=ws, request_id=rid)

    await asyncio.gather(*(one(i, a) for i, a in enumerate(actuals)))

    assert await _committed(ws) == sum(actuals)
    # 所有预扣释放干净
    leftover = await r.get(billing.reserved_key(ws))
    assert leftover is None or int(leftover) == 0
