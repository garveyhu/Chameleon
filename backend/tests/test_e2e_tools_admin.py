"""P18.2 PR #23 E2E：tool_instances admin CRUD + catalog + ToolNode enabled gate"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import (
    Role,
    ToolInstance,
    User,
    UserRole,
)
from chameleon.core.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-tools-{rand}"
    password = "TestAdminPwd123!"
    async with AsyncSessionLocal() as s:
        admin_role_id = (
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
        s.add(UserRole(user_id=u.id, role_id=admin_role_id))
        await s.commit()
        uid = u.id

    r = await client.post(
        "/v1/auth/login",
        json={"username": username, "password": password},
    )
    token = r.json()["data"]["access_token"]
    yield token

    async with AsyncSessionLocal() as s:
        await s.execute(delete(UserRole).where(UserRole.user_id == uid))
        await s.execute(delete(User).where(User.id == uid))
        await s.commit()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tool_instances():
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(delete(ToolInstance))
        await s.commit()


# ── catalog ───────────────────────────────────────────────


async def test_catalog_lists_builtins(
    client: AsyncClient, admin_token: str
):
    r = await client.get(
        "/v1/admin/tools/catalog",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    items = r.json()["data"]
    keys = {it["tool_key"] for it in items}
    assert {"http", "sql"}.issubset(keys)
    # 每个都带 parameters_schema
    http_it = next(it for it in items if it["tool_key"] == "http")
    assert http_it["parameters_schema"]["type"] == "object"
    assert http_it["default_enabled"] is True
    sql_it = next(it for it in items if it["tool_key"] == "sql")
    assert sql_it["default_enabled"] is False
    # 初始无实例
    assert all(it["instance_id"] is None for it in items)


# ── CRUD ──────────────────────────────────────────────────


async def test_create_instance(client: AsyncClient, admin_token: str):
    r = await client.post(
        "/v1/admin/tools",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "tool_key": "http",
            "name": "Public HTTP",
            "config": {"allowed_url_prefixes": ["https://api.example.com/"]},
        },
    )
    assert r.status_code == 200, r.text
    item = r.json()["data"]
    assert item["tool_key"] == "http"
    assert item["enabled"] is True  # http default_enabled=True
    assert item["config"]["allowed_url_prefixes"] == [
        "https://api.example.com/"
    ]


async def test_create_instance_unknown_tool_key(
    client: AsyncClient, admin_token: str
):
    r = await client.post(
        "/v1/admin/tools",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"tool_key": "ghost-tool", "name": "x"},
    )
    body = r.json()
    assert body["success"] is False
    assert "未注册" in body["message"]


async def test_create_sql_instance_default_disabled(
    client: AsyncClient, admin_token: str
):
    """SQLTool default_enabled=False，create 后 enabled 应为 False"""
    r = await client.post(
        "/v1/admin/tools",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"tool_key": "sql", "name": "Read DB"},
    )
    assert r.status_code == 200
    item = r.json()["data"]
    assert item["tool_key"] == "sql"
    assert item["enabled"] is False


async def test_create_duplicate_rejected(
    client: AsyncClient, admin_token: str
):
    await client.post(
        "/v1/admin/tools",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"tool_key": "http", "name": "a"},
    )
    r = await client.post(
        "/v1/admin/tools",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"tool_key": "http", "name": "b"},
    )
    body = r.json()
    assert body["success"] is False
    assert "已配过" in body["message"]


async def test_update_and_delete(client: AsyncClient, admin_token: str):
    cr = await client.post(
        "/v1/admin/tools",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"tool_key": "http", "name": "x"},
    )
    iid = cr.json()["data"]["id"]

    # 更新 enabled
    r = await client.post(
        f"/v1/admin/tools/{iid}/update",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"enabled": False, "name": "x-renamed"},
    )
    item = r.json()["data"]
    assert item["enabled"] is False
    assert item["name"] == "x-renamed"

    # 删除
    dr = await client.post(
        f"/v1/admin/tools/{iid}/delete",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert dr.status_code == 200

    list_r = await client.get(
        "/v1/admin/tools",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert iid not in [it["id"] for it in list_r.json()["data"]]
