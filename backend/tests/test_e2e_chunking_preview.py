"""P18.4 PR #26 E2E：chunking-preview 实时预览端点"""

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
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-cp-{rand}"
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


async def test_requires_auth(client: AsyncClient):
    r = await client.post(
        "/v1/admin/kbs/chunking-preview",
        json={"text": "hello", "strategy": {"mode": "fixed"}},
    )
    assert r.status_code == 401


async def test_fixed_mode(client: AsyncClient, admin_token: str):
    text = "x" * 250
    r = await client.post(
        "/v1/admin/kbs/chunking-preview",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "text": text,
            "strategy": {"mode": "fixed", "chunk_size": 100, "overlap": 20},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["mode"] == "fixed"
    assert body["count"] >= 3
    for ch in body["chunks"]:
        assert ch["char_count"] <= 100
        assert ch["token_count_approx"] >= 1


async def test_paragraph_mode(client: AsyncClient, admin_token: str):
    text = "段一\n\n段二有内容\n\n段三"
    r = await client.post(
        "/v1/admin/kbs/chunking-preview",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"text": text, "strategy": {"mode": "paragraph"}},
    )
    body = r.json()["data"]
    assert body["count"] == 3
    assert [c["content"] for c in body["chunks"]] == ["段一", "段二有内容", "段三"]


async def test_token_mode(client: AsyncClient, admin_token: str):
    text = "hello world " * 100
    r = await client.post(
        "/v1/admin/kbs/chunking-preview",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "text": text,
            "strategy": {"mode": "token", "chunk_size": 50, "overlap": 10},
        },
    )
    body = r.json()["data"]
    assert body["mode"] == "token"
    assert body["count"] > 1


async def test_invalid_mode_rejected(client: AsyncClient, admin_token: str):
    r = await client.post(
        "/v1/admin/kbs/chunking-preview",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"text": "x", "strategy": {"mode": "ghost"}},
    )
    body = r.json()
    assert body["success"] is False
    assert "unsupported chunk mode" in body["message"] or "ghost" in body["message"]


async def test_empty_text_returns_zero_chunks(
    client: AsyncClient, admin_token: str
):
    r = await client.post(
        "/v1/admin/kbs/chunking-preview",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"text": "   \n  ", "strategy": {"mode": "fixed"}},
    )
    body = r.json()["data"]
    assert body["count"] == 0
