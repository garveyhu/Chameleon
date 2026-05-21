"""P7 嵌入式 E2E 测试

覆盖：
- admin 创建 embed_config（指定 allowed_origins）
- 业务端 GET /config：合法 origin 200 / 非法 origin 403 / 无 origin（同源）200
- 业务端 POST /session：颁 token + 进 Redis
- 业务端 POST /invoke：token + origin 校验 + 调对应 mock-echo agent
- 限流：6 次 invoke → 第 6 次 429
"""

from __future__ import annotations

import secrets

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import (
    Agent,
    App,
    EmbedConfig,
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
    username = f"e2e-p7-admin-{rand}"
    password = "TestAdminPwd123!"

    async with AsyncSessionLocal() as s:
        admin_role_id = (
            await s.execute(select(Role.id).where(Role.code == "admin"))
        ).scalar_one()
        user = User(
            username=username,
            password_hash=hash_password(password),
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
async def embed_setup(client: AsyncClient, admin_token: str):
    """建一个 embed_config 关联 mock-echo agent + 临时 app"""
    headers = {"Authorization": f"Bearer {admin_token}"}
    rand = secrets.token_hex(3)

    # 临时 app
    r = await client.post(
        "/v1/admin/apps",
        headers=headers,
        json={"app_key": f"e2e-p7-{rand}", "name": "p7"},
    )
    app_id = r.json()["data"]["id"]

    # 找 mock-echo agent（conftest 注入的）— 它没有 DB 行，要建一个
    async with AsyncSessionLocal() as s:
        agent = (
            await s.execute(
                select(Agent).where(Agent.agent_key == "mock-echo")
            )
        ).scalar_one_or_none()
        if agent is None:
            # 借 echo-native 当测试 agent
            agent = (
                await s.execute(
                    select(Agent).where(Agent.agent_key == "example-echo-native")
                )
            ).scalar_one()
        agent_id = agent.id

    # 创 embed_config
    r = await client.post(
        "/v1/admin/embed-configs",
        headers=headers,
        json={
            "name": f"test-embed-{rand}",
            "agent_id": agent_id,
            "app_id": app_id,
            "allowed_origins": ["https://allowed.example.com"],
            "ui_config": {"theme": "light"},
            "behavior": {"welcome_message": "你好"},
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    yield {
        "embed_key": data["embed_key"],
        "config_id": data["id"],
        "app_id": app_id,
        "agent_id": agent_id,
    }

    # cleanup
    async with AsyncSessionLocal() as s:
        await s.execute(
            delete(EmbedConfig).where(EmbedConfig.id == data["id"])
        )
        await s.execute(delete(App).where(App.id == app_id))
        await s.commit()


# ── 1. config 端点 ────────────────────────────────────────


async def test_get_config_with_allowed_origin(
    client: AsyncClient, embed_setup
):
    embed_key = embed_setup["embed_key"]
    r = await client.get(
        f"/v1/embed/{embed_key}/config",
        headers={"Origin": "https://allowed.example.com"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["embed_key"] == embed_key
    assert data["welcome_message"] == "你好"
    assert data["ui_config"] == {"theme": "light"}


async def test_get_config_rejects_evil_origin(
    client: AsyncClient, embed_setup
):
    embed_key = embed_setup["embed_key"]
    r = await client.get(
        f"/v1/embed/{embed_key}/config",
        headers={"Origin": "https://evil.example.com"},
    )
    assert r.status_code == 403
    assert r.json()["code"] == 40310  # PermissionDenied


async def test_get_config_allows_no_origin(client: AsyncClient, embed_setup):
    """同源场景（无 Origin header）→ 允许"""
    embed_key = embed_setup["embed_key"]
    r = await client.get(f"/v1/embed/{embed_key}/config")
    assert r.status_code == 200


async def test_get_config_unknown_key_404(client: AsyncClient):
    r = await client.get("/v1/embed/emb_nonexistent/config")
    assert r.status_code == 404


# ── 2. session 端点 ───────────────────────────────────────


async def test_create_session_returns_token(client: AsyncClient, embed_setup):
    embed_key = embed_setup["embed_key"]
    r = await client.post(
        f"/v1/embed/{embed_key}/session",
        headers={"Origin": "https://allowed.example.com"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["session_token"]
    assert data["expires_in"] == 3600


async def test_create_session_evil_origin_rejected(
    client: AsyncClient, embed_setup
):
    embed_key = embed_setup["embed_key"]
    r = await client.post(
        f"/v1/embed/{embed_key}/session",
        headers={"Origin": "https://evil.example.com"},
    )
    assert r.status_code == 403


# ── 3. invoke 端点 ────────────────────────────────────────


async def test_invoke_with_valid_session(
    client: AsyncClient, embed_setup
):
    embed_key = embed_setup["embed_key"]
    # 拿 session
    r = await client.post(
        f"/v1/embed/{embed_key}/session",
        headers={"Origin": "https://allowed.example.com"},
    )
    token = r.json()["data"]["session_token"]

    # invoke
    r = await client.post(
        f"/v1/embed/{embed_key}/invoke",
        headers={"Origin": "https://allowed.example.com"},
        json={"session_token": token, "input": "hello"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["answer"]
    assert data["session_id"]


async def test_invoke_with_invalid_token(client: AsyncClient, embed_setup):
    embed_key = embed_setup["embed_key"]
    r = await client.post(
        f"/v1/embed/{embed_key}/invoke",
        headers={"Origin": "https://allowed.example.com"},
        json={"session_token": "fake-token", "input": "hi"},
    )
    assert r.status_code == 401
    assert r.json()["code"] == 40112  # JwtInvalid


async def test_invoke_rate_limit(client: AsyncClient, embed_setup):
    """单 token 1 分钟内 > 5 次 → 限流"""
    embed_key = embed_setup["embed_key"]
    r = await client.post(
        f"/v1/embed/{embed_key}/session",
        headers={"Origin": "https://allowed.example.com"},
    )
    token = r.json()["data"]["session_token"]

    for i in range(5):
        r = await client.post(
            f"/v1/embed/{embed_key}/invoke",
            headers={"Origin": "https://allowed.example.com"},
            json={"session_token": token, "input": f"hi-{i}"},
        )
        assert r.status_code == 200, f"invoke #{i+1} failed: {r.text}"

    # 第 6 次：限流
    r = await client.post(
        f"/v1/embed/{embed_key}/invoke",
        headers={"Origin": "https://allowed.example.com"},
        json={"session_token": token, "input": "hi-6"},
    )
    assert r.status_code == 429
    assert r.json()["code"] == 42901  # AppRateLimit
