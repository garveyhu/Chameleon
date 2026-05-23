"""P19.3 PR #38 E2E: /v1/admin/workspaces CRUD + members"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import (
    Membership,
    Role,
    User,
    UserRole,
    Workspace,
)
from chameleon.core.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-wsadm-{rand}"
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
async def alt_user_id():
    """供 add_member 使用的另一个用户"""
    rand = secrets.token_hex(3)
    async with AsyncSessionLocal() as s:
        u = User(
            username=f"e2e-target-{rand}",
            password_hash=hash_password("x"),
            status="active",
            must_change_password=False,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        yield u.id

    async with AsyncSessionLocal() as s:
        await s.execute(delete(Membership).where(Membership.user_id == u.id))
        await s.execute(delete(User).where(User.id == u.id))
        await s.commit()


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_extra_workspaces():
    """每个测试后清掉非 default workspace + membership 防交叉"""
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(
            delete(Membership).where(Membership.workspace_id != 1)
        )
        await s.execute(delete(Workspace).where(Workspace.id != 1))
        await s.commit()


def _hdr(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


# ── workspace CRUD ──────────────────────────────────────


async def test_list_includes_default(client: AsyncClient, admin_token: str):
    r = await client.get("/v1/admin/workspaces", headers=_hdr(admin_token))
    assert r.status_code == 200, r.text
    keys = {w["workspace_key"] for w in r.json()["data"]}
    assert "default" in keys


async def test_create_then_list(client: AsyncClient, admin_token: str):
    key = f"acme-{secrets.token_hex(2)}"
    r = await client.post(
        "/v1/admin/workspaces",
        headers=_hdr(admin_token),
        json={"workspace_key": key, "name": "Acme 工作区", "plan": "pro"},
    )
    assert r.status_code == 200, r.text
    ws = r.json()["data"]
    assert ws["workspace_key"] == key
    assert ws["plan"] == "pro"

    list_r = await client.get(
        "/v1/admin/workspaces", headers=_hdr(admin_token)
    )
    assert key in {w["workspace_key"] for w in list_r.json()["data"]}


async def test_create_rejects_duplicate_key(
    client: AsyncClient, admin_token: str
):
    key = f"dup-{secrets.token_hex(2)}"
    r1 = await client.post(
        "/v1/admin/workspaces",
        headers=_hdr(admin_token),
        json={"workspace_key": key, "name": "x"},
    )
    assert r1.status_code == 200
    r2 = await client.post(
        "/v1/admin/workspaces",
        headers=_hdr(admin_token),
        json={"workspace_key": key, "name": "y"},
    )
    assert r2.status_code in (400, 500)


async def test_update_workspace_plan(client: AsyncClient, admin_token: str):
    r = await client.post(
        "/v1/admin/workspaces",
        headers=_hdr(admin_token),
        json={"workspace_key": f"upd-{secrets.token_hex(2)}", "name": "x"},
    )
    wid = r.json()["data"]["id"]
    ur = await client.post(
        f"/v1/admin/workspaces/{wid}/update",
        headers=_hdr(admin_token),
        json={"plan": "enterprise", "name": "Renamed"},
    )
    assert ur.json()["data"]["plan"] == "enterprise"
    assert ur.json()["data"]["name"] == "Renamed"


async def test_delete_default_rejected(client: AsyncClient, admin_token: str):
    r = await client.post(
        "/v1/admin/workspaces/1/delete", headers=_hdr(admin_token)
    )
    assert r.status_code in (400, 500)
    assert r.json()["success"] is False


async def test_delete_external_succeeds(
    client: AsyncClient, admin_token: str
):
    cr = await client.post(
        "/v1/admin/workspaces",
        headers=_hdr(admin_token),
        json={"workspace_key": f"del-{secrets.token_hex(2)}", "name": "x"},
    )
    wid = cr.json()["data"]["id"]
    dr = await client.post(
        f"/v1/admin/workspaces/{wid}/delete", headers=_hdr(admin_token)
    )
    assert dr.status_code == 200
    # 列表里看不到（软删）
    lr = await client.get(
        "/v1/admin/workspaces", headers=_hdr(admin_token)
    )
    assert wid not in [w["id"] for w in lr.json()["data"]]


# ── members CRUD ────────────────────────────────────────


async def test_add_member_then_list(
    client: AsyncClient, admin_token: str, alt_user_id: int
):
    cr = await client.post(
        "/v1/admin/workspaces",
        headers=_hdr(admin_token),
        json={"workspace_key": f"mem-{secrets.token_hex(2)}", "name": "x"},
    )
    wid = cr.json()["data"]["id"]

    ar = await client.post(
        f"/v1/admin/workspaces/{wid}/members",
        headers=_hdr(admin_token),
        json={"user_id": alt_user_id, "role": "member"},
    )
    assert ar.status_code == 200, ar.text
    assert ar.json()["data"]["role"] == "member"
    assert ar.json()["data"]["username"]

    lr = await client.get(
        f"/v1/admin/workspaces/{wid}/members", headers=_hdr(admin_token)
    )
    assert len(lr.json()["data"]) == 1


async def test_add_member_duplicate_rejected(
    client: AsyncClient, admin_token: str, alt_user_id: int
):
    cr = await client.post(
        "/v1/admin/workspaces",
        headers=_hdr(admin_token),
        json={"workspace_key": f"dup-{secrets.token_hex(2)}", "name": "x"},
    )
    wid = cr.json()["data"]["id"]

    await client.post(
        f"/v1/admin/workspaces/{wid}/members",
        headers=_hdr(admin_token),
        json={"user_id": alt_user_id, "role": "member"},
    )
    r2 = await client.post(
        f"/v1/admin/workspaces/{wid}/members",
        headers=_hdr(admin_token),
        json={"user_id": alt_user_id, "role": "admin"},
    )
    assert r2.status_code in (400, 500)


async def test_update_member_role(
    client: AsyncClient, admin_token: str, alt_user_id: int
):
    cr = await client.post(
        "/v1/admin/workspaces",
        headers=_hdr(admin_token),
        json={"workspace_key": f"upd-{secrets.token_hex(2)}", "name": "x"},
    )
    wid = cr.json()["data"]["id"]
    ar = await client.post(
        f"/v1/admin/workspaces/{wid}/members",
        headers=_hdr(admin_token),
        json={"user_id": alt_user_id, "role": "member"},
    )
    mid = ar.json()["data"]["id"]

    ur = await client.post(
        f"/v1/admin/workspaces/{wid}/members/{mid}/update",
        headers=_hdr(admin_token),
        json={"role": "admin"},
    )
    assert ur.json()["data"]["role"] == "admin"


async def test_remove_member(
    client: AsyncClient, admin_token: str, alt_user_id: int
):
    cr = await client.post(
        "/v1/admin/workspaces",
        headers=_hdr(admin_token),
        json={"workspace_key": f"rm-{secrets.token_hex(2)}", "name": "x"},
    )
    wid = cr.json()["data"]["id"]
    ar = await client.post(
        f"/v1/admin/workspaces/{wid}/members",
        headers=_hdr(admin_token),
        json={"user_id": alt_user_id, "role": "member"},
    )
    mid = ar.json()["data"]["id"]

    rr = await client.post(
        f"/v1/admin/workspaces/{wid}/members/{mid}/delete",
        headers=_hdr(admin_token),
    )
    assert rr.status_code == 200

    lr = await client.get(
        f"/v1/admin/workspaces/{wid}/members", headers=_hdr(admin_token)
    )
    assert lr.json()["data"] == []
