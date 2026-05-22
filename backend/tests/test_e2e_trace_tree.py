"""P17.C1 trace tree API E2E

覆盖：
- 单节点（root，无子）
- 多层嵌套（trace → agent → generation × N）
- request_id 不存在 → 404
- 已删除的孤立 children 不影响（root parent_id null）
"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import App, CallLog, Role, User, UserRole
from chameleon.core.utils.passwords import hash_password
from chameleon.system.api_key.service import record_call
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-tt-{rand}"
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
async def trace_app():
    """临时 app + 一些预置 call_logs 形成嵌套结构

    trace_root (type=trace)
    ├─ agent_step (type=agent)
    │   ├─ gen_1 (type=generation)
    │   └─ tool_call (type=tool)
    └─ embedding (type=embedding)
    """
    suffix = secrets.token_hex(3)
    app_key = f"trace-app-{suffix}"
    root_rid = f"trace-root-{suffix}"
    agent_rid = f"trace-agent-{suffix}"
    gen_rid = f"trace-gen-{suffix}"
    tool_rid = f"trace-tool-{suffix}"
    emb_rid = f"trace-emb-{suffix}"

    async with AsyncSessionLocal() as s:
        s.add(App(app_key=app_key, name="trace test", status="active"))
        await s.flush()

        # root
        await record_call(
            s, request_id=root_rid, app_id=app_key, agent_key="example",
            session_id=None, stream=False, success=True, code=200,
            error_message=None, duration_ms=500,
            observation_type="trace",
        )
        # agent
        await record_call(
            s, request_id=agent_rid, app_id=app_key, agent_key="example",
            session_id=None, stream=False, success=True, code=200,
            error_message=None, duration_ms=300, parent_id=root_rid,
            observation_type="agent",
        )
        # gen + tool 在 agent 下
        await record_call(
            s, request_id=gen_rid, app_id=app_key, agent_key="example",
            session_id=None, stream=False, success=True, code=200,
            error_message=None, duration_ms=200, parent_id=agent_rid,
            observation_type="generation",
            prompt_tokens=50, completion_tokens=80, total_tokens=130,
        )
        await record_call(
            s, request_id=tool_rid, app_id=app_key, agent_key="example",
            session_id=None, stream=False, success=True, code=200,
            error_message=None, duration_ms=50, parent_id=agent_rid,
            observation_type="tool",
        )
        # embedding 平级 agent
        await record_call(
            s, request_id=emb_rid, app_id=app_key, agent_key="example",
            session_id=None, stream=False, success=True, code=200,
            error_message=None, duration_ms=80, parent_id=root_rid,
            observation_type="embedding",
        )
        await s.commit()

    yield {
        "app_key": app_key,
        "root": root_rid,
        "agent": agent_rid,
        "gen": gen_rid,
        "tool": tool_rid,
        "emb": emb_rid,
    }

    async with AsyncSessionLocal() as s:
        await s.execute(delete(CallLog).where(CallLog.app_id == app_key))
        await s.execute(delete(App).where(App.app_key == app_key))
        await s.commit()


# ── 鉴权 ──────────────────────────────────────────────────


async def test_tree_requires_auth(client: AsyncClient):
    r = await client.get("/v1/admin/call-logs/x/tree")
    assert r.status_code == 401


# ── 嵌套树结构 ────────────────────────────────────────────


async def test_tree_full_structure(
    client: AsyncClient, admin_token: str, trace_app: dict
):
    r = await client.get(
        f"/v1/admin/call-logs/{trace_app['root']}/tree",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    tree = r.json()["data"]

    # root 节点
    assert tree["request_id"] == trace_app["root"]
    assert tree["parent_id"] is None
    assert tree["observation_type"] == "trace"
    # 直接子两条：agent + embedding
    assert len(tree["children"]) == 2
    child_types = {c["observation_type"] for c in tree["children"]}
    assert child_types == {"agent", "embedding"}

    # agent 节点下面 generation + tool
    agent_node = next(c for c in tree["children"] if c["observation_type"] == "agent")
    assert len(agent_node["children"]) == 2
    grandchild_types = {g["observation_type"] for g in agent_node["children"]}
    assert grandchild_types == {"generation", "tool"}

    # generation 节点 token 字段被透传
    gen_node = next(
        g for g in agent_node["children"] if g["observation_type"] == "generation"
    )
    assert gen_node["prompt_tokens"] == 50
    assert gen_node["completion_tokens"] == 80
    assert gen_node["total_tokens"] == 130


async def test_tree_query_by_subtree_root(
    client: AsyncClient, admin_token: str, trace_app: dict
):
    """传入子节点 request_id 时，以该子节点为根返子树"""
    r = await client.get(
        f"/v1/admin/call-logs/{trace_app['agent']}/tree",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    tree = r.json()["data"]
    assert tree["request_id"] == trace_app["agent"]
    # 直接子 2 个，没有 root / embedding
    assert len(tree["children"]) == 2
    rids = {c["request_id"] for c in tree["children"]}
    assert rids == {trace_app["gen"], trace_app["tool"]}


async def test_tree_leaf_node(
    client: AsyncClient, admin_token: str, trace_app: dict
):
    """叶子节点：无 children"""
    r = await client.get(
        f"/v1/admin/call-logs/{trace_app['gen']}/tree",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    tree = r.json()["data"]
    assert tree["children"] == []
    assert tree["observation_type"] == "generation"


async def test_tree_not_found(client: AsyncClient, admin_token: str):
    r = await client.get(
        "/v1/admin/call-logs/not-exist-rid/tree",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.json()["success"] is False
