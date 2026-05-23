"""P22.3 PR #78 E2E: Graph publish 流程 + 版本递增 + freeze"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import Graph, Role, User, UserRole
from chameleon.core.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-pub-{rand}"
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
async def _clean_graphs():
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(
            delete(Graph).where(Graph.graph_key.like("e2e-pub-%"))
        )
        await s.commit()


def _hdr(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _minimal_spec() -> dict:
    return {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "end", "type": "end"},
        ],
        "edges": [{"id": "e1", "source": "start", "target": "end"}],
    }


# ── publish ─────────────────────────────────────────────


async def test_publish_first_time(client: AsyncClient, admin_token: str):
    suffix = secrets.token_hex(3)
    cr = await client.post(
        "/v1/admin/graphs",
        headers=_hdr(admin_token),
        json={
            "graph_key": f"e2e-pub-{suffix}",
            "name": "pub-test",
            "spec": _minimal_spec(),
        },
    )
    assert cr.status_code == 200, cr.text
    gid = cr.json()["data"]["id"]
    assert cr.json()["data"]["published_version"] == 0
    assert cr.json()["data"]["published_at"] is None

    pr = await client.post(
        f"/v1/admin/graphs/{gid}/publish",
        headers=_hdr(admin_token),
    )
    assert pr.status_code == 200, pr.text
    data = pr.json()["data"]
    assert data["published_version"] == 1
    assert data["published_at"] is not None
    assert data["published_spec"] is not None
    # published_spec 应该等于 draft spec 的快照
    assert data["published_spec"]["nodes"] == _minimal_spec()["nodes"]


async def test_publish_version_increments(
    client: AsyncClient, admin_token: str
):
    suffix = secrets.token_hex(3)
    cr = await client.post(
        "/v1/admin/graphs",
        headers=_hdr(admin_token),
        json={
            "graph_key": f"e2e-pub-{suffix}",
            "name": "ver-test",
            "spec": _minimal_spec(),
        },
    )
    gid = cr.json()["data"]["id"]

    for expected_ver in (1, 2, 3):
        pr = await client.post(
            f"/v1/admin/graphs/{gid}/publish",
            headers=_hdr(admin_token),
        )
        assert pr.status_code == 200
        assert pr.json()["data"]["published_version"] == expected_ver


async def test_publish_freezes_current_draft(
    client: AsyncClient, admin_token: str
):
    """publish 后改 draft；published_spec 不变（红线：published 不被覆盖）"""
    suffix = secrets.token_hex(3)
    cr = await client.post(
        "/v1/admin/graphs",
        headers=_hdr(admin_token),
        json={
            "graph_key": f"e2e-pub-{suffix}",
            "name": "freeze-test",
            "spec": _minimal_spec(),
        },
    )
    gid = cr.json()["data"]["id"]
    await client.post(
        f"/v1/admin/graphs/{gid}/publish", headers=_hdr(admin_token)
    )

    # 改 draft
    new_spec = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "noop", "type": "noop"},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "noop"},
            {"id": "e2", "source": "noop", "target": "end"},
        ],
    }
    await client.post(
        f"/v1/admin/graphs/{gid}/update",
        headers=_hdr(admin_token),
        json={"spec": new_spec},
    )
    gr = await client.get(
        f"/v1/admin/graphs/{gid}", headers=_hdr(admin_token)
    )
    data = gr.json()["data"]
    assert len(data["spec"]["nodes"]) == 3  # draft 已改
    # published_spec 仍是老的 2 节点
    assert len(data["published_spec"]["nodes"]) == 2
    assert data["published_version"] == 1


async def test_publish_unknown_graph_404(
    client: AsyncClient, admin_token: str
):
    r = await client.post(
        "/v1/admin/graphs/999999999/publish", headers=_hdr(admin_token)
    )
    assert r.status_code in (400, 404, 500)


# ── list 仍返 published_version ────────────────────────


async def test_list_includes_published_fields(
    client: AsyncClient, admin_token: str
):
    suffix = secrets.token_hex(3)
    cr = await client.post(
        "/v1/admin/graphs",
        headers=_hdr(admin_token),
        json={
            "graph_key": f"e2e-pub-{suffix}",
            "name": "list-test",
            "spec": _minimal_spec(),
        },
    )
    gid = cr.json()["data"]["id"]
    await client.post(
        f"/v1/admin/graphs/{gid}/publish", headers=_hdr(admin_token)
    )

    lr = await client.get(
        "/v1/admin/graphs", headers=_hdr(admin_token)
    )
    target = [
        g for g in lr.json()["data"] if g["graph_key"] == f"e2e-pub-{suffix}"
    ]
    assert len(target) == 1
    assert target[0]["published_version"] == 1
    assert target[0]["published_at"] is not None
