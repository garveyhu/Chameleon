"""P22.5 PR #83 E2E：应用市场 template gallery"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import AppTemplate, Role, User, UserRole
from chameleon.data.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-tmpl-{rand}"
    password = "TestPwd123!"
    async with AsyncSessionLocal() as s:
        rid = (
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
        s.add(UserRole(user_id=u.id, role_id=rid))
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


@pytest_asyncio.fixture(autouse=True)
async def _clean_templates():
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(delete(AppTemplate))
        await s.commit()


def _hdr(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


# ── create + verified=False 红线 ─────────────────────────


async def test_create_template_unverified_by_default(
    client: AsyncClient, admin_token: str
):
    r = await client.post(
        "/v1/admin/app-templates",
        headers=_hdr(admin_token),
        json={
            "name": "客服 Agent",
            "category": "agent",
            "spec_json": {"agent_key": "demo"},
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    # 红线：默认 verified=False
    assert data["verified"] is False
    assert data["downloads"] == 0


async def test_create_template_unknown_category(
    client: AsyncClient, admin_token: str
):
    r = await client.post(
        "/v1/admin/app-templates",
        headers=_hdr(admin_token),
        json={
            "name": "x",
            "category": "not-a-category",
            "spec_json": {},
        },
    )
    assert r.status_code in (400, 422, 500)


# ── list 默认 only_verified=True 红线 ───────────────────


async def test_list_default_only_verified(
    client: AsyncClient, admin_token: str
):
    # 造 1 unverified + 1 verified
    cr1 = await client.post(
        "/v1/admin/app-templates",
        headers=_hdr(admin_token),
        json={"name": "unverified", "category": "agent", "spec_json": {}},
    )
    tid1 = cr1.json()["data"]["id"]

    cr2 = await client.post(
        "/v1/admin/app-templates",
        headers=_hdr(admin_token),
        json={"name": "to-verify", "category": "rag", "spec_json": {}},
    )
    tid2 = cr2.json()["data"]["id"]
    await client.post(
        f"/v1/admin/app-templates/{tid2}/verify",
        headers=_hdr(admin_token),
        json={"verified": True},
    )

    # 默认 list 只返 verified
    r = await client.get(
        "/v1/admin/app-templates", headers=_hdr(admin_token)
    )
    items = r.json()["data"]
    names = {it["name"] for it in items}
    assert "to-verify" in names
    assert "unverified" not in names

    # 显式 only_verified=False 全返
    r2 = await client.get(
        "/v1/admin/app-templates?only_verified=false",
        headers=_hdr(admin_token),
    )
    names_all = {it["name"] for it in r2.json()["data"]}
    assert "unverified" in names_all
    assert "to-verify" in names_all

    # category 过滤
    r3 = await client.get(
        "/v1/admin/app-templates?only_verified=false&category=agent",
        headers=_hdr(admin_token),
    )
    cats = {it["category"] for it in r3.json()["data"]}
    assert cats == {"agent"}

    _ = tid1


# ── verify 切换 ────────────────────────────────────────


async def test_verify_toggle_changes_visibility(
    client: AsyncClient, admin_token: str
):
    cr = await client.post(
        "/v1/admin/app-templates",
        headers=_hdr(admin_token),
        json={"name": "vt", "category": "assistant", "spec_json": {}},
    )
    tid = cr.json()["data"]["id"]

    vr1 = await client.post(
        f"/v1/admin/app-templates/{tid}/verify",
        headers=_hdr(admin_token),
        json={"verified": True},
    )
    assert vr1.json()["data"]["verified"] is True

    vr2 = await client.post(
        f"/v1/admin/app-templates/{tid}/verify",
        headers=_hdr(admin_token),
        json={"verified": False},
    )
    assert vr2.json()["data"]["verified"] is False


# ── install 增加 downloads ─────────────────────────────


async def test_install_increments_downloads(
    client: AsyncClient, admin_token: str
):
    cr = await client.post(
        "/v1/admin/app-templates",
        headers=_hdr(admin_token),
        json={"name": "inst", "category": "workflow", "spec_json": {"x": 1}},
    )
    tid = cr.json()["data"]["id"]

    for expected in (1, 2, 3):
        r = await client.post(
            f"/v1/admin/app-templates/{tid}/install",
            headers=_hdr(admin_token),
            json={},
        )
        assert r.status_code == 200, r.text

    g = await client.get(
        f"/v1/admin/app-templates/{tid}", headers=_hdr(admin_token)
    )
    assert g.json()["data"]["downloads"] == 3


async def test_install_unknown_template_404(
    client: AsyncClient, admin_token: str
):
    r = await client.post(
        "/v1/admin/app-templates/999999999/install",
        headers=_hdr(admin_token),
        json={},
    )
    assert r.status_code in (400, 404, 500)


# ── delete ─────────────────────────────────────────────


async def test_delete_template(client: AsyncClient, admin_token: str):
    cr = await client.post(
        "/v1/admin/app-templates",
        headers=_hdr(admin_token),
        json={"name": "del", "category": "agent", "spec_json": {}},
    )
    tid = cr.json()["data"]["id"]
    dr = await client.post(
        f"/v1/admin/app-templates/{tid}/delete",
        headers=_hdr(admin_token),
    )
    assert dr.status_code == 200
    gr = await client.get(
        f"/v1/admin/app-templates/{tid}", headers=_hdr(admin_token)
    )
    assert gr.status_code in (400, 404, 500)
