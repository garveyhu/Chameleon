"""P19.3 PR #37: workspace 鉴权 + 业务过滤端到端

验证：
- 非 admin 用户仅能看到自己 workspace 的 agents
- create 强制写当前 workspace_id
- X-Workspace-Id header 切换视角
- admin 默认看全；指定 header 后切到具体 ws
- 跨 ws 访问越权 → 403
"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import (
    Agent,
    Membership,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
    Workspace,
)
from chameleon.core.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty


# ── fixtures ────────────────────────────────────────────


async def _make_user(
    role_code: str, *, prefix: str = "ws"
) -> tuple[int, str, str]:
    rand = secrets.token_hex(3)
    username = f"e2e-{prefix}-{rand}"
    password = "TestPwd123!"
    async with AsyncSessionLocal() as s:
        role_id = (
            await s.execute(select(Role.id).where(Role.code == role_code))
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
        await s.refresh(u)
        return u.id, username, password


async def _ensure_developer_has_agents_perms() -> None:
    """auth 测试 fixture cleanup 会 `DELETE FROM permissions WHERE code LIKE 'agents:%'`，
    导致 developer 角色的 RolePermission 行失效；这里把 agents:read/write 重新挂回去"""
    async with AsyncSessionLocal() as s:
        dev_role_id = (
            await s.execute(select(Role.id).where(Role.code == "developer"))
        ).scalar_one_or_none()
        if dev_role_id is None:
            return
        for code in ("agents:read", "agents:write"):
            p = (
                await s.execute(select(Permission).where(Permission.code == code))
            ).scalar_one_or_none()
            if p is None:
                continue
            exists = (
                await s.execute(
                    select(RolePermission).where(
                        RolePermission.role_id == dev_role_id,
                        RolePermission.permission_id == p.id,
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                s.add(RolePermission(role_id=dev_role_id, permission_id=p.id))
        await s.commit()


async def _login(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post(
        "/v1/auth/login",
        json={"username": username, "password": password},
    )
    return r.json()["data"]["access_token"]


@pytest_asyncio.fixture
async def two_workspaces_and_users(client: AsyncClient):
    """建 2 个 workspace + 1 admin + 2 个 developer（各自属一个 ws）"""
    await run_seed_if_empty()

    # auth 测试可能删过 agents:* perm 行，导致 developer 角色失去 agents:write；
    # 这里幂等补齐，确保后续 fixture 创建的 dev 用户能通过 require_permission
    await _ensure_developer_has_agents_perms()

    async with AsyncSessionLocal() as s:
        ws_a = Workspace(
            workspace_key=f"ws-a-{secrets.token_hex(2)}",
            name="Alpha 工作区",
        )
        ws_b = Workspace(
            workspace_key=f"ws-b-{secrets.token_hex(2)}",
            name="Beta 工作区",
        )
        s.add_all([ws_a, ws_b])
        await s.commit()
        await s.refresh(ws_a)
        await s.refresh(ws_b)
        ws_a_id, ws_b_id = ws_a.id, ws_b.id

    admin_id, admin_user, admin_pw = await _make_user("admin", prefix="ws-adm")
    dev_a_id, dev_a_user, dev_a_pw = await _make_user("developer", prefix="ws-a-dev")
    dev_b_id, dev_b_user, dev_b_pw = await _make_user("developer", prefix="ws-b-dev")

    async with AsyncSessionLocal() as s:
        s.add_all(
            [
                Membership(
                    user_id=dev_a_id,
                    workspace_id=ws_a_id,
                    role="member",
                ),
                Membership(
                    user_id=dev_b_id,
                    workspace_id=ws_b_id,
                    role="member",
                ),
            ]
        )
        await s.commit()

    admin_token = await _login(client, admin_user, admin_pw)
    dev_a_token = await _login(client, dev_a_user, dev_a_pw)
    dev_b_token = await _login(client, dev_b_user, dev_b_pw)

    ctx = {
        "ws_a_id": ws_a_id,
        "ws_b_id": ws_b_id,
        "admin_id": admin_id,
        "dev_a_id": dev_a_id,
        "dev_b_id": dev_b_id,
        "admin_token": admin_token,
        "dev_a_token": dev_a_token,
        "dev_b_token": dev_b_token,
    }
    yield ctx

    async with AsyncSessionLocal() as s:
        for uid in (admin_id, dev_a_id, dev_b_id):
            await s.execute(delete(UserRole).where(UserRole.user_id == uid))
            await s.execute(delete(Membership).where(Membership.user_id == uid))
            await s.execute(delete(User).where(User.id == uid))
        await s.execute(
            delete(Agent).where(Agent.workspace_id.in_([ws_a_id, ws_b_id]))
        )
        await s.execute(
            delete(Workspace).where(Workspace.id.in_([ws_a_id, ws_b_id]))
        )
        await s.commit()


def _hdr(token: str, ws_id: int | None = None) -> dict[str, str]:
    h = {"Authorization": f"Bearer {token}"}
    if ws_id is not None:
        h["X-Workspace-Id"] = str(ws_id)
    return h


async def _create_agent(client: AsyncClient, hdr: dict[str, str], key_suffix: str):
    return await client.post(
        "/v1/admin/agents",
        headers=hdr,
        json={
            "agent_key": f"iso-{key_suffix}",
            "name": f"iso test {key_suffix}",
            "source": "dify",
            "provider_id": None,
            "config": {},
            "tags": [],
        },
    )


# ── 非 admin 严格隔离 ───────────────────────────────────


async def test_dev_a_creates_in_ws_a_dev_b_cannot_see(
    client: AsyncClient, two_workspaces_and_users: dict
):
    ctx = two_workspaces_and_users

    # dev_a 创建一个 agent（workspace_id 应自动写为 ws_a）
    r = await _create_agent(
        client, _hdr(ctx["dev_a_token"]), f"a-{secrets.token_hex(2)}"
    )
    assert r.status_code == 200, r.text
    created = r.json()["data"]

    # dev_a 列表 → 能看到
    list_a = await client.get(
        "/v1/admin/agents", headers=_hdr(ctx["dev_a_token"])
    )
    keys_a = {a["agent_key"] for a in list_a.json()["data"]}
    assert created["agent_key"] in keys_a

    # dev_b 列表 → 看不到
    list_b = await client.get(
        "/v1/admin/agents", headers=_hdr(ctx["dev_b_token"])
    )
    keys_b = {a["agent_key"] for a in list_b.json()["data"]}
    assert created["agent_key"] not in keys_b

    # 数据库层验证：workspace_id 写对了
    async with AsyncSessionLocal() as s:
        row = (
            await s.execute(
                select(Agent).where(Agent.agent_key == created["agent_key"])
            )
        ).scalar_one()
        assert row.workspace_id == ctx["ws_a_id"]


async def test_dev_cross_workspace_header_rejected(
    client: AsyncClient, two_workspaces_and_users: dict
):
    """dev_a 用 X-Workspace-Id 指向 ws_b → 403"""
    ctx = two_workspaces_and_users
    r = await client.get(
        "/v1/admin/agents",
        headers=_hdr(ctx["dev_a_token"], ws_id=ctx["ws_b_id"]),
    )
    assert r.status_code == 403


# ── admin 默认看全 + 可切换视角 ────────────────────────


async def test_admin_sees_both_workspaces_by_default(
    client: AsyncClient, two_workspaces_and_users: dict
):
    ctx = two_workspaces_and_users
    # 各 workspace 都用各自 token 创建一个 agent
    await _create_agent(
        client, _hdr(ctx["dev_a_token"]), f"adm-a-{secrets.token_hex(2)}"
    )
    await _create_agent(
        client, _hdr(ctx["dev_b_token"]), f"adm-b-{secrets.token_hex(2)}"
    )

    r = await client.get(
        "/v1/admin/agents", headers=_hdr(ctx["admin_token"])
    )
    assert r.status_code == 200
    rows = r.json()["data"]
    # admin 不带 header → 看全：含两个 workspace 的 agent
    ws_ids = {a.get("workspace_id") for a in rows}
    assert str(ctx["ws_a_id"]) in ws_ids and str(ctx["ws_b_id"]) in ws_ids


async def test_admin_can_scope_to_ws_a_via_header(
    client: AsyncClient, two_workspaces_and_users: dict
):
    ctx = two_workspaces_and_users
    a_key = f"hdr-a-{secrets.token_hex(2)}"
    b_key = f"hdr-b-{secrets.token_hex(2)}"
    await _create_agent(client, _hdr(ctx["dev_a_token"]), a_key)
    await _create_agent(client, _hdr(ctx["dev_b_token"]), b_key)

    r = await client.get(
        "/v1/admin/agents",
        headers=_hdr(ctx["admin_token"], ws_id=ctx["ws_a_id"]),
    )
    keys = {a["agent_key"] for a in r.json()["data"]}
    assert f"iso-{a_key}" in keys
    assert f"iso-{b_key}" not in keys


# ── header 非法 ─────────────────────────────────────────


async def test_header_non_int_rejected(
    client: AsyncClient, two_workspaces_and_users: dict
):
    ctx = two_workspaces_and_users
    r = await client.get(
        "/v1/admin/agents",
        headers={
            "Authorization": f"Bearer {ctx['admin_token']}",
            "X-Workspace-Id": "not-a-number",
        },
    )
    assert r.status_code == 403


async def test_header_all_keyword_admin_sees_all(
    client: AsyncClient, two_workspaces_and_users: dict
):
    """X-Workspace-Id=all → admin 显式表达全量"""
    ctx = two_workspaces_and_users
    await _create_agent(
        client, _hdr(ctx["dev_a_token"]), f"all-a-{secrets.token_hex(2)}"
    )
    await _create_agent(
        client, _hdr(ctx["dev_b_token"]), f"all-b-{secrets.token_hex(2)}"
    )

    r = await client.get(
        "/v1/admin/agents",
        headers={
            "Authorization": f"Bearer {ctx['admin_token']}",
            "X-Workspace-Id": "all",
        },
    )
    rows = r.json()["data"]
    ws_ids = {a.get("workspace_id") for a in rows}
    assert str(ctx["ws_a_id"]) in ws_ids and str(ctx["ws_b_id"]) in ws_ids
