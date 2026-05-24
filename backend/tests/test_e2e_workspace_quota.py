"""P19.3 PR #39 E2E：workspace 配额检查 + 累加 + reset"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select, update

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import (
    Role,
    User,
    UserRole,
    Workspace,
    WorkspaceQuota,
)
from chameleon.core.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty
from chameleon.system.workspaces import quota_service


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-quota-{rand}"
    password = "TestPwd123!"
    async with AsyncSessionLocal() as s:
        role_id = (
            await s.execute(select(Role.id).where(Role.code == "admin"))
        ).scalar_one()
        u = User(
            username=username,
            password_hash=hash_password(password),
            status="active",
            must_change_password=False,
        )
        s.add(u)
        await s.flush()
        s.add(UserRole(user_id=u.id, role_id=role_id))
        await s.commit()
        uid = u.id

    r = await client.post(
        "/v1/auth/login",
        json={"username": username, "password": password},
    )
    yield r.json()["data"]["access_token"]

    async with AsyncSessionLocal() as s:
        await s.execute(delete(UserRole).where(UserRole.user_id == uid))
        await s.execute(delete(User).where(User.id == uid))
        await s.commit()


@pytest_asyncio.fixture
async def temp_workspace():
    """临时 workspace + quota 行"""
    async with AsyncSessionLocal() as s:
        ws = Workspace(
            workspace_key=f"quota-{secrets.token_hex(2)}",
            name="quota test",
        )
        s.add(ws)
        await s.commit()
        await s.refresh(ws)
        wid = ws.id
    yield wid
    async with AsyncSessionLocal() as s:
        await s.execute(delete(WorkspaceQuota).where(WorkspaceQuota.workspace_id == wid))
        await s.execute(delete(Workspace).where(Workspace.id == wid))
        await s.commit()


def _hdr(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


# ── 服务层单测 ───────────────────────────────────────────


async def test_assert_within_request_quota_passes_when_unlimited(
    temp_workspace: int,
):
    async with AsyncSessionLocal() as s:
        # 默认 quota=NULL → 不限
        await quota_service.assert_within_request_quota(s, temp_workspace)


async def test_assert_blocks_when_request_exhausted(temp_workspace: int):
    from chameleon.core.api.exceptions import BusinessError, ResultCode

    async with AsyncSessionLocal() as s:
        q = await quota_service.get_or_create_quota(s, temp_workspace)
        q.request_quota_daily = 1
        q.request_used_today = 1
        await s.commit()

    import pytest

    with pytest.raises(BusinessError) as exc:
        async with AsyncSessionLocal() as s:
            await quota_service.assert_within_request_quota(s, temp_workspace)
    assert exc.value.code == ResultCode.WorkspaceQuotaExceeded


async def test_assert_blocks_when_token_exhausted(temp_workspace: int):
    from chameleon.core.api.exceptions import BusinessError

    async with AsyncSessionLocal() as s:
        q = await quota_service.get_or_create_quota(s, temp_workspace)
        q.token_quota_monthly = 100
        q.token_used_current_month = 100
        await s.commit()

    import pytest

    with pytest.raises(BusinessError):
        async with AsyncSessionLocal() as s:
            await quota_service.assert_within_request_quota(s, temp_workspace)


async def test_increment_usage_accumulates(temp_workspace: int):
    async with AsyncSessionLocal() as s:
        await quota_service.increment_usage(
            s, temp_workspace, total_tokens=50, requests=1
        )
        await s.commit()
    async with AsyncSessionLocal() as s:
        await quota_service.increment_usage(
            s, temp_workspace, total_tokens=70, requests=2
        )
        await s.commit()
    async with AsyncSessionLocal() as s:
        snap = await quota_service.snapshot(s, temp_workspace)
    assert snap.token_used_current_month == 120
    assert snap.request_used_today == 3


async def test_increment_noop_when_ws_is_none():
    async with AsyncSessionLocal() as s:
        # 不应抛
        await quota_service.increment_usage(
            s, None, total_tokens=999, requests=10
        )


# ── lazy reset 跨期 ─────────────────────────────────────


async def test_lazy_reset_daily_request_counter(temp_workspace: int):
    """reset_at 设为昨天 → 下次 check 触发 daily reset"""
    yesterday = datetime.now(timezone.utc) - timedelta(days=1, hours=2)
    async with AsyncSessionLocal() as s:
        await s.execute(
            update(WorkspaceQuota)
            .where(WorkspaceQuota.workspace_id == temp_workspace)
            .values(
                request_quota_daily=10,
                request_used_today=10,
                reset_at=yesterday,
            )
        )
        await s.commit()

    # check 内部触发 _maybe_reset_periods → request_used_today 应清零
    async with AsyncSessionLocal() as s:
        await quota_service.assert_within_request_quota(s, temp_workspace)
        await s.commit()

    async with AsyncSessionLocal() as s:
        snap = await quota_service.snapshot(s, temp_workspace)
    assert snap.request_used_today == 0


async def test_lazy_reset_monthly_token_counter(temp_workspace: int):
    """reset_at 设为上月 → 跨月 reset token_used_current_month"""
    now = datetime.now(timezone.utc)
    # 上个月同一天（避免 31 号问题，用月初）
    last_month = now.replace(day=1) - timedelta(days=5)
    async with AsyncSessionLocal() as s:
        await s.execute(
            update(WorkspaceQuota)
            .where(WorkspaceQuota.workspace_id == temp_workspace)
            .values(
                token_quota_monthly=10000,
                token_used_current_month=9000,
                request_used_today=0,
                reset_at=last_month,
            )
        )
        await s.commit()

    async with AsyncSessionLocal() as s:
        await quota_service.assert_within_request_quota(s, temp_workspace)
        await s.commit()

    async with AsyncSessionLocal() as s:
        snap = await quota_service.snapshot(s, temp_workspace)
    assert snap.token_used_current_month == 0


# ── admin API ───────────────────────────────────────────


async def test_admin_get_quota(
    client: AsyncClient, admin_token: str, temp_workspace: int
):
    r = await client.get(
        f"/v1/admin/workspaces/{temp_workspace}/quota",
        headers=_hdr(admin_token),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["workspace_id"] == str(temp_workspace)
    assert data["token_used_current_month"] == 0


async def test_admin_update_quota_and_reset(
    client: AsyncClient, admin_token: str, temp_workspace: int
):
    # 先 increment 一些
    async with AsyncSessionLocal() as s:
        await quota_service.increment_usage(
            s, temp_workspace, total_tokens=500, requests=3
        )
        await s.commit()

    r = await client.post(
        f"/v1/admin/workspaces/{temp_workspace}/quota/update",
        headers=_hdr(admin_token),
        json={
            "token_quota_monthly": 100000,
            "request_quota_daily": 1000,
            "reset_used": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["token_quota_monthly"] == 100000
    assert data["request_quota_daily"] == 1000
    assert data["token_used_current_month"] == 0
    assert data["request_used_today"] == 0


# ── HTTP 状态码 ────────────────────────────────────────


async def test_quota_exceeded_returns_429_via_global_handler(
    client: AsyncClient, admin_token: str, temp_workspace: int
):
    """配额 service 内部 BusinessError(WorkspaceQuotaExceeded) → 全局 handler 应映射 429"""
    # 给 ws 配 request_quota_daily=1，已用满 → admin update 配额接口本身不被限
    # 这里测的是当 BusinessError 抛出时，code_to_http_status 映射到 429
    from chameleon.core.api.exceptions import code_to_http_status, ResultCode

    assert code_to_http_status(int(ResultCode.WorkspaceQuotaExceeded)) == 429
