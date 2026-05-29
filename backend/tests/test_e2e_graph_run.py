"""P18.1 graph run 持久化 + trace 串联 E2E（PR #21）

覆盖：
- POST /v1/admin/graphs/{id}/run 跑通最小 graph（start→end）
- graph_runs 行落地 + status=success + duration
- 对应 call_logs 行：trace 根 + 每节点 child（parent_id 串联）
- GET /tree/{root_rid} 返完整嵌套结构
- 跑失败时 status=failed + error.message 落库
"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import (
    CallLog,
    Graph,
    GraphRun,
    Role,
    User,
    UserRole,
)
from chameleon.core.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-gr-{rand}"
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
        user_id = u.id

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
async def smoke_graph():
    """创建最小 graph：start → noop → end"""
    key = f"e2e-gr-{secrets.token_hex(3)}"
    spec = {
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "m", "type": "noop"},
            {"id": "e", "type": "end"},
        ],
        "edges": [
            {"id": "1", "source": "s", "target": "m"},
            {"id": "2", "source": "m", "target": "e"},
        ],
    }
    async with AsyncSessionLocal() as s:
        g = Graph(graph_key=key, name="e2e graph", spec=spec, enabled=True)
        s.add(g)
        await s.flush()
        await s.commit()
        gid = g.id
    yield {"id": gid, "key": key}

    async with AsyncSessionLocal() as s:
        # 清 call_logs（graph 跑后留下的）
        runs = (
            (
                await s.execute(
                    select(GraphRun).where(GraphRun.graph_id == gid)
                )
            )
            .scalars()
            .all()
        )
        rids = [r.request_id for r in runs]
        if rids:
            await s.execute(
                delete(CallLog).where(
                    CallLog.parent_id.in_(rids) | CallLog.request_id.in_(rids)
                )
            )
        await s.execute(delete(GraphRun).where(GraphRun.graph_id == gid))
        await s.execute(delete(Graph).where(Graph.id == gid))
        await s.commit()


# ── /run 持久化 ───────────────────────────────────────────


async def test_run_persists_graph_run_and_node_spans(
    client: AsyncClient, admin_token: str, smoke_graph: dict
):
    r = await client.post(
        f"/v1/admin/graphs/{smoke_graph['id']}/run",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"input": {"hello": "world"}},
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["status"] == "success"
    assert body["node_count"] == 3
    assert body["duration_ms"] >= 0
    root_rid = body["request_id"]
    assert root_rid.startswith(f"graph-{smoke_graph['id']}-")

    # graph_node_runs 已删 —— 节点明细落在 call_logs span 行（根 trace 的直接子、
    # 非 generation），request_id = f"{root}.{node_id}"。
    async with AsyncSessionLocal() as s:
        spans = (
            (
                await s.execute(
                    select(CallLog).where(
                        CallLog.parent_id == root_rid,
                        CallLog.observation_type != "generation",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(spans) == 3
        assert all(sp.request_id.startswith(f"{root_rid}.") for sp in spans)
        assert all(sp.success for sp in spans)


async def test_run_creates_call_logs_with_trace_chain(
    client: AsyncClient, admin_token: str, smoke_graph: dict
):
    r = await client.post(
        f"/v1/admin/graphs/{smoke_graph['id']}/run",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"input": {}},
    )
    root_rid = r.json()["data"]["request_id"]

    # call_logs 应有：1 个 trace 根 + 3 个子节点
    async with AsyncSessionLocal() as s:
        root = (
            await s.execute(
                select(CallLog).where(CallLog.request_id == root_rid)
            )
        ).scalar_one()
        assert root.parent_id is None
        assert root.observation_type == "trace"
        assert root.success is True

        children = (
            (
                await s.execute(
                    select(CallLog).where(CallLog.parent_id == root_rid)
                )
            )
            .scalars()
            .all()
        )
        assert len(children) == 3
        # observation_type 映射：start/noop/end 都是 span
        types = {c.observation_type for c in children}
        assert types == {"span"}


async def test_run_tree_endpoint_returns_nested_structure(
    client: AsyncClient, admin_token: str, smoke_graph: dict
):
    """跑完 graph 后 P17.C1 的 /call-logs/{rid}/tree 能返完整结构"""
    r = await client.post(
        f"/v1/admin/graphs/{smoke_graph['id']}/run",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"input": {"q": "hi"}},
    )
    root_rid = r.json()["data"]["request_id"]

    tree_r = await client.get(
        f"/v1/admin/call-logs/{root_rid}/tree",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert tree_r.status_code == 200, tree_r.text
    tree = tree_r.json()["data"]
    assert tree["request_id"] == root_rid
    assert tree["observation_type"] == "trace"
    assert len(tree["children"]) == 3


# ── /runs 列表 ────────────────────────────────────────────


async def test_list_runs_returns_latest_first(
    client: AsyncClient, admin_token: str, smoke_graph: dict
):
    for _ in range(2):
        await client.post(
            f"/v1/admin/graphs/{smoke_graph['id']}/run",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"input": {}},
        )
    r = await client.get(
        f"/v1/admin/graphs/{smoke_graph['id']}/runs",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    runs = r.json()["data"]
    assert len(runs) == 2
    assert runs[0]["created_at"] >= runs[1]["created_at"]


# ── 失败传播 ──────────────────────────────────────────────


async def test_run_persists_failure(
    client: AsyncClient, admin_token: str
):
    """spec 含半截图（dangling 节点）→ 跑时报错，graph_run.status=failed"""
    key = f"e2e-fail-{secrets.token_hex(3)}"
    bad_spec = {
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "x", "type": "noop"},  # 没有出边
            {"id": "e", "type": "end"},  # 只能通过 s 直达
        ],
        "edges": [
            {"id": "1", "source": "s", "target": "x"},
            {"id": "2", "source": "s", "target": "e"},
            # 注意：没有 x → e，执行器会从 s 第一条边 (→x) 走到 x，发现无出边报错
        ],
    }
    # 先创建（合法 spec）
    cr = await client.post(
        "/v1/admin/graphs",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"graph_key": key, "name": "fail graph", "spec": bad_spec},
    )
    assert cr.status_code == 200, cr.text
    gid = cr.json()["data"]["id"]

    try:
        r = await client.post(
            f"/v1/admin/graphs/{gid}/run",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"input": {}},
        )
        body = r.json()["data"]
        assert body["status"] == "failed"
        assert body["error"] is not None
    finally:
        async with AsyncSessionLocal() as s:
            runs = (
                (
                    await s.execute(
                        select(GraphRun).where(GraphRun.graph_id == gid)
                    )
                )
                .scalars()
                .all()
            )
            rids = [r.request_id for r in runs]
            if rids:
                await s.execute(
                    delete(CallLog).where(
                        CallLog.parent_id.in_(rids)
                        | CallLog.request_id.in_(rids)
                    )
                )
            await s.execute(
                delete(GraphRun).where(GraphRun.graph_id == gid)
            )
            await s.execute(delete(Graph).where(Graph.id == gid))
            await s.commit()
