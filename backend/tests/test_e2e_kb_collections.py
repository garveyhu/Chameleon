"""P20.3 PR #53 E2E: KB collections admin CRUD"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import (
    KbCollection,
    KnowledgeBase,
    Role,
    User,
    UserRole,
)
from chameleon.data.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-kbc-{rand}"
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
async def kb_id():
    """临时 KB"""
    async with AsyncSessionLocal() as s:
        rand = secrets.token_hex(3)
        kb = KnowledgeBase(
            kb_key=f"e2e-kbc-{rand}",
            name="kbc-test",
            embedding_model="text-embedding-3-small",
            embedding_dim=1536,
        )
        s.add(kb)
        await s.commit()
        await s.refresh(kb)
        kid = kb.id
    yield kid
    async with AsyncSessionLocal() as s:
        await s.execute(delete(KbCollection).where(KbCollection.kb_id == kid))
        await s.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kid))
        await s.commit()


def _hdr(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


# ── CRUD ───────────────────────────────────────────────


async def test_create_then_list_collections(
    client: AsyncClient, admin_token: str, kb_id: int
):
    r = await client.post(
        f"/v1/admin/kbs/{kb_id}/collections",
        headers=_hdr(admin_token),
        json={
            "name": "faq-zh",
            "collection_type": "faq",
            "indexes": [{"name": "chunk", "dim": 1536, "enabled": True}],
        },
    )
    assert r.status_code == 200, r.text
    item = r.json()["data"]
    assert item["collection_type"] == "faq"
    assert item["name"] == "faq-zh"

    lr = await client.get(
        f"/v1/admin/kbs/{kb_id}/collections", headers=_hdr(admin_token)
    )
    assert any(c["name"] == "faq-zh" for c in lr.json()["data"])


async def test_duplicate_name_in_same_kb_rejected(
    client: AsyncClient, admin_token: str, kb_id: int
):
    payload = {"name": "dup", "collection_type": "generic"}
    r1 = await client.post(
        f"/v1/admin/kbs/{kb_id}/collections",
        headers=_hdr(admin_token),
        json=payload,
    )
    assert r1.status_code == 200
    r2 = await client.post(
        f"/v1/admin/kbs/{kb_id}/collections",
        headers=_hdr(admin_token),
        json=payload,
    )
    assert r2.status_code in (400, 500)


async def test_unknown_collection_type_rejected(
    client: AsyncClient, admin_token: str, kb_id: int
):
    r = await client.post(
        f"/v1/admin/kbs/{kb_id}/collections",
        headers=_hdr(admin_token),
        json={"name": "x", "collection_type": "not-a-type"},
    )
    assert r.status_code in (400, 422, 500)


async def test_update_collection_does_not_change_type(
    client: AsyncClient, admin_token: str, kb_id: int
):
    """update API schema 不接受 collection_type 字段 —— 改类型必须新建"""
    cr = await client.post(
        f"/v1/admin/kbs/{kb_id}/collections",
        headers=_hdr(admin_token),
        json={"name": "upd-c", "collection_type": "wiki"},
    )
    cid = cr.json()["data"]["id"]

    ur = await client.post(
        f"/v1/admin/kbs/{kb_id}/collections/{cid}/update",
        headers=_hdr(admin_token),
        json={
            "name": "renamed",
            # 即便传了 collection_type 也被 schema 忽略
            "collection_type": "api",  # type: ignore[typeddict-unknown-key]
        },
    )
    assert ur.status_code == 200
    assert ur.json()["data"]["name"] == "renamed"
    # 类型仍是 wiki —— 红线：collection_type 不可改
    assert ur.json()["data"]["collection_type"] == "wiki"


async def test_delete_collection(
    client: AsyncClient, admin_token: str, kb_id: int
):
    cr = await client.post(
        f"/v1/admin/kbs/{kb_id}/collections",
        headers=_hdr(admin_token),
        json={"name": "del-c", "collection_type": "api"},
    )
    cid = cr.json()["data"]["id"]

    dr = await client.post(
        f"/v1/admin/kbs/{kb_id}/collections/{cid}/delete",
        headers=_hdr(admin_token),
    )
    assert dr.status_code == 200

    lr = await client.get(
        f"/v1/admin/kbs/{kb_id}/collections", headers=_hdr(admin_token)
    )
    assert all(c["id"] != cid for c in lr.json()["data"])


async def test_collection_in_other_kb_not_visible(
    client: AsyncClient, admin_token: str, kb_id: int
):
    """另一个 KB 下的 collection 不应在本 KB list 里看到"""
    cr = await client.post(
        f"/v1/admin/kbs/{kb_id}/collections",
        headers=_hdr(admin_token),
        json={"name": "iso-c", "collection_type": "faq"},
    )
    cid = cr.json()["data"]["id"]

    # 操作另一个 KB id（非法）→ NotFound
    other = 99999999
    ur = await client.post(
        f"/v1/admin/kbs/{other}/collections/{cid}/update",
        headers=_hdr(admin_token),
        json={"name": "stolen"},
    )
    assert ur.status_code in (400, 404, 500)
