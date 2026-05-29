"""P6 admin API 综合 E2E 测试

覆盖 8 大模块的 happy path + 权限守卫 + 路由总数。
fixture：用 seed 出的默认 admin 登录拿 token。
"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import Role, User, UserRole
from chameleon.data.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    """临时建一个 admin 角色用户，登录返 token；测试完清理"""
    await run_seed_if_empty()  # 确保 admin role 已经 seed

    rand = secrets.token_hex(3)
    username = f"e2e-p6-admin-{rand}"
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
    assert r.status_code == 200, r.text
    token = r.json()["data"]["access_token"]

    yield token

    async with AsyncSessionLocal() as s:
        await s.execute(delete(UserRole).where(UserRole.user_id == user_id))
        await s.execute(delete(User).where(User.id == user_id))
        await s.commit()


# ── 健康性：端点全部能查 ─────────────────────────────────


async def test_users_list_ok(client: AsyncClient, admin_token: str):
    r = await client.get(
        "/v1/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["total"] >= 1  # 至少 admin 用户
    assert any(u["username"] == "admin" for u in body["items"])


async def test_roles_list_includes_built_in(
    client: AsyncClient, admin_token: str
):
    r = await client.get(
        "/v1/admin/roles", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert r.status_code == 200
    codes = {r_["code"] for r_ in r.json()["data"]}
    assert {"admin", "developer", "viewer"} <= codes


async def test_permissions_list_has_resource_filter(
    client: AsyncClient, admin_token: str
):
    r = await client.get(
        "/v1/admin/permissions?resource=agents",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    perms = r.json()["data"]
    assert all(p["resource"] == "agents" for p in perms)


async def test_providers_list_includes_seeded(
    client: AsyncClient, admin_token: str
):
    r = await client.get(
        "/v1/admin/providers",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    codes = {p["code"] for p in r.json()["data"]}
    # seed 必带 qwen / openai / deepseek（model.json）
    assert {"qwen", "openai", "deepseek"} <= codes


async def test_models_list_includes_seeded(client: AsyncClient, admin_token: str):
    r = await client.get(
        "/v1/admin/models", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert r.status_code == 200
    codes = {m["code"] for m in r.json()["data"]}
    assert {"qwen-plus", "deepseek-chat"} <= codes


async def test_agents_list_includes_local(client: AsyncClient, admin_token: str):
    r = await client.get(
        "/v1/admin/agents", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert r.status_code == 200
    keys = {a["agent_key"] for a in r.json()["data"]}
    assert "qwen-chat" in keys
    assert "example-echo-langgraph" in keys


async def test_kbs_list_ok(client: AsyncClient, admin_token: str):
    r = await client.get(
        "/v1/admin/kbs", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert r.status_code == 200


async def test_dashboard_overview_ok(client: AsyncClient, admin_token: str):
    r = await client.get(
        "/v1/admin/dashboard/overview",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert "total_calls_24h" in data
    assert "success_rate_24h" in data


async def test_dashboard_timeseries_buckets(
    client: AsyncClient, admin_token: str
):
    r = await client.get(
        "/v1/admin/dashboard/timeseries?granularity=hour&hours=24",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["granularity"] == "hour"


async def test_audit_logs_list_ok(client: AsyncClient, admin_token: str):
    r = await client.get(
        "/v1/admin/audit-logs",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200


# ── CRUD 闭环：创建 → 改 → 删 ────────────────────────────


async def test_agent_disable_enable_loop(
    client: AsyncClient, admin_token: str
):
    headers = {"Authorization": f"Bearer {admin_token}"}
    # 取本地 echo-native（不预设 enabled 状态，先确保 enabled → disable → enable）
    r = await client.get("/v1/admin/agents?source=local", headers=headers)
    target = next(
        a for a in r.json()["data"] if a["agent_key"] == "example-echo-native"
    )
    aid = target["id"]

    # 先确保 enabled（前面的 test 可能 disable 过）
    r = await client.post(f"/v1/admin/agents/{aid}/enable", headers=headers)
    assert r.status_code == 200
    assert r.json()["data"]["enabled"] is True

    r = await client.post(f"/v1/admin/agents/{aid}/disable", headers=headers)
    assert r.status_code == 200
    assert r.json()["data"]["enabled"] is False

    r = await client.post(f"/v1/admin/agents/{aid}/enable", headers=headers)
    assert r.status_code == 200
    assert r.json()["data"]["enabled"] is True


# 注：provider 级 test 端点已移除 —— provider 只是凭证容器，可用性测试改在 model 级。
# 见 chameleon.system.models.api.test_model（POST /v1/admin/models/{id}/test）。
