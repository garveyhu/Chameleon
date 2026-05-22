"""P17.F1.2 schema 注册集成 E2E

验证：
- provider/agent 子包 import 时自动 register 了 schema
- /v1/admin/providers 列表的 agent_config_schema_name 字段按 kind 推导
- 实际 dump schema 内容包含期望字段
"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import Provider, Role, User, UserRole
from chameleon.core.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-schema-int-{rand}"
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
async def dify_provider():
    """临时创建一个 kind=dify 的 provider，用完删"""
    code = f"e2e-dify-{secrets.token_hex(3)}"
    async with AsyncSessionLocal() as s:
        p = Provider(code=code, kind="dify", name="E2E DIFY", enabled=True)
        s.add(p)
        await s.flush()
        await s.commit()
        pid = p.id
    yield pid
    async with AsyncSessionLocal() as s:
        await s.execute(delete(Provider).where(Provider.id == pid))
        await s.commit()


# ── 自动注册校验 ────────────────────────────────────────────


async def test_provider_schemas_registered(
    client: AsyncClient, admin_token: str
):
    """init_registry 跑过后，3 个 provider agent_config 都在列表里"""
    r = await client.get(
        "/v1/admin/schemas?prefix=provider.",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    names = {it["name"] for it in r.json()["data"]}
    assert "provider.dify.agent_config" in names
    assert "provider.fastgpt.agent_config" in names
    assert "provider.local.agent_config" in names


async def test_dify_agent_config_schema_content(
    client: AsyncClient, admin_token: str
):
    r = await client.get(
        "/v1/admin/schemas/provider.dify.agent_config",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    schema = r.json()["data"]
    props = schema["properties"]
    # 关键字段
    assert "endpoint" in props
    assert "api_key_env" in props
    assert "mode" in props
    # mode 是 Literal["chat", "workflow"] → 应该有 enum
    # Pydantic v2 把 Literal 放到 $defs 里
    mode_prop = props["mode"]
    if "$ref" in mode_prop:
        ref_name = mode_prop["$ref"].rsplit("/", 1)[-1]
        assert set(schema["$defs"][ref_name]["enum"]) == {"chat", "workflow"}
    else:
        assert set(mode_prop.get("enum", [])) == {"chat", "workflow"}
    # required: endpoint + api_key_env
    assert "endpoint" in schema["required"]
    assert "api_key_env" in schema["required"]


async def test_dify_schema_inline_refs(client: AsyncClient, admin_token: str):
    """inline_refs=true 后 mode 直接展开 enum，没 $ref"""
    r = await client.get(
        "/v1/admin/schemas/provider.dify.agent_config?inline_refs=true",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    schema = r.json()["data"]
    assert "$defs" not in schema
    mode_prop = schema["properties"]["mode"]
    assert set(mode_prop["enum"]) == {"chat", "workflow"}


# ── /providers 列表暴露 schema name ─────────────────────────


async def test_providers_list_attaches_schema_name(
    client: AsyncClient, admin_token: str, dify_provider: int
):
    r = await client.get(
        "/v1/admin/providers",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    providers = r.json()["data"]
    dify_p = next(p for p in providers if p["id"] == dify_provider)
    assert dify_p["agent_config_schema_name"] == "provider.dify.agent_config"

    # llm provider 没有注册 schema → 应为 None
    llm_ps = [p for p in providers if p["kind"] == "llm"]
    if llm_ps:
        assert all(p["agent_config_schema_name"] is None for p in llm_ps)


async def test_agent_input_schema_registered(
    client: AsyncClient, admin_token: str
):
    """echo agent 的 input schema 也被自动注册"""
    r = await client.get(
        "/v1/admin/schemas?prefix=agent.",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    names = {it["name"] for it in r.json()["data"]}
    assert "agent.example-echo-native.input" in names
