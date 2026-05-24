"""P17.A1.2 abilities admin API E2E"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import Ability, Channel, Provider, Role, User, UserRole
from chameleon.core.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-ab-{rand}"
    password = "TestAdminPwd123!"

    async with AsyncSessionLocal() as s:
        admin_role_id = (
            await s.execute(select(Role.id).where(Role.code == "admin"))
        ).scalar_one()
        user = User(
            username=username,
            password_hash=hash_password(password),
            status="active",
            must_change_password=False,
        )
        s.add(user)
        await s.flush()
        s.add(UserRole(user_id=user.id, role_id=admin_role_id))
        await s.commit()
        user_id = user.id

    r = await client.post(
        "/v1/auth/login",
        json={"username": username, "password": password},
    )
    token = r.json()["data"]["access_token"]
    yield token

    async with AsyncSessionLocal() as s:
        await s.execute(delete(UserRole).where(UserRole.user_id == user_id))
        await s.execute(delete(User).where(User.id == user_id))
        await s.commit()


@pytest_asyncio.fixture
async def tmp_channel():
    """临时 provider + channel；测试完清理"""
    rand = secrets.token_hex(3)
    async with AsyncSessionLocal() as s:
        provider = Provider(code=f"ab-prov-{rand}", kind="llm", name="x", enabled=True)
        s.add(provider)
        await s.flush()
        ch = Channel(provider_id=provider.id, name="primary", status="enabled")
        s.add(ch)
        await s.flush()
        await s.commit()
        ch_id, prov_id = ch.id, provider.id
    yield {"channel_id": ch_id, "provider_id": prov_id}
    async with AsyncSessionLocal() as s:
        await s.execute(delete(Ability).where(Ability.channel_id == ch_id))
        await s.execute(delete(Channel).where(Channel.id == ch_id))
        await s.execute(delete(Provider).where(Provider.id == prov_id))
        await s.commit()


# ── 鉴权 ──────────────────────────────────────────────────


async def test_abilities_requires_auth(client: AsyncClient):
    r = await client.get("/v1/admin/abilities")
    assert r.status_code == 401


# ── CRUD happy path ───────────────────────────────────────


async def test_create_ability(client: AsyncClient, admin_token: str, tmp_channel):
    r = await client.post(
        "/v1/admin/abilities",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "model_code": "test-model-a",
            "channel_id": tmp_channel["channel_id"],
            "priority": 5,
            "weight": 3,
        },
    )
    assert r.status_code == 200, r.text
    a = r.json()["data"]
    assert a["model_code"] == "test-model-a"
    assert str(a["channel_id"]) == str(tmp_channel["channel_id"])
    assert a["priority"] == 5
    assert a["weight"] == 3
    assert a["enabled"] is True
    assert a["group_id"] is None
    # join 字段
    assert a["channel_name"] == "primary"
    assert a["provider_code"]


async def test_create_duplicate_route_rejected(
    client: AsyncClient, admin_token: str, tmp_channel
):
    """同 (group, model_code, channel) 三元组只能存在一条"""
    payload = {
        "model_code": "dup-model",
        "channel_id": tmp_channel["channel_id"],
    }
    r1 = await client.post(
        "/v1/admin/abilities",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=payload,
    )
    assert r1.status_code == 200

    r2 = await client.post(
        "/v1/admin/abilities",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=payload,
    )
    assert r2.json()["success"] is False
    assert "重复" in r2.json()["message"]


async def test_create_with_bad_channel(client: AsyncClient, admin_token: str):
    r = await client.post(
        "/v1/admin/abilities",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"model_code": "x", "channel_id": 999999999999},
    )
    assert r.json()["success"] is False
    assert "channel" in r.json()["message"]


async def test_list_filter_by_model_code(
    client: AsyncClient, admin_token: str, tmp_channel
):
    suffix = secrets.token_hex(3)
    mc = f"filter-model-{suffix}"
    await client.post(
        "/v1/admin/abilities",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"model_code": mc, "channel_id": tmp_channel["channel_id"]},
    )
    r = await client.get(
        f"/v1/admin/abilities?model_code={mc}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    items = r.json()["data"]
    assert len(items) == 1
    assert items[0]["model_code"] == mc


async def test_list_filter_global_only(
    client: AsyncClient, admin_token: str, tmp_channel
):
    """group_id=0 表示仅查全局 ability（group_id IS NULL）"""
    suffix = secrets.token_hex(3)
    mc = f"global-{suffix}"
    # 一条全局，一条 group=42
    await client.post(
        "/v1/admin/abilities",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"model_code": mc, "channel_id": tmp_channel["channel_id"]},
    )
    await client.post(
        "/v1/admin/abilities",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "model_code": mc,
            "channel_id": tmp_channel["channel_id"],
            "group_id": 42,
        },
    )
    r = await client.get(
        f"/v1/admin/abilities?model_code={mc}&group_id=0",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    items = r.json()["data"]
    assert len(items) == 1
    assert items[0]["group_id"] is None


async def test_update_ability(client: AsyncClient, admin_token: str, tmp_channel):
    cr = await client.post(
        "/v1/admin/abilities",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"model_code": "upd-model", "channel_id": tmp_channel["channel_id"]},
    )
    aid = cr.json()["data"]["id"]

    r = await client.post(
        f"/v1/admin/abilities/{aid}/update",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"priority": 99, "enabled": False},
    )
    assert r.status_code == 200
    a = r.json()["data"]
    assert a["priority"] == 99
    assert a["enabled"] is False


async def test_delete_ability(client: AsyncClient, admin_token: str, tmp_channel):
    cr = await client.post(
        "/v1/admin/abilities",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"model_code": "del-model", "channel_id": tmp_channel["channel_id"]},
    )
    aid = cr.json()["data"]["id"]

    r = await client.post(
        f"/v1/admin/abilities/{aid}/delete",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200

    # 更新已删的应该 404
    r2 = await client.post(
        f"/v1/admin/abilities/{aid}/update",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"priority": 1},
    )
    assert r2.status_code == 404
