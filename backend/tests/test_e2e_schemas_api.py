"""P17.F1.1 schemas admin API E2E

覆盖：
- 401（未鉴权）
- 列表 + 前缀过滤
- 详情 hit / miss
- inline_refs 模式
"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from chameleon.core.schema import register
from chameleon.core.schema.registry import _reset_for_tests
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import Role, User, UserRole
from chameleon.data.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    """临时建一个 admin 角色用户，登录返 token；测试完清理"""
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-schemas-{rand}"
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


@pytest_asyncio.fixture(autouse=True)
async def _isolated_registry():
    """每个测试都从干净 registry 开始，跑完恢复"""
    # 保存现有快照
    from chameleon.core.schema import list_all
    snapshot = list_all()
    _reset_for_tests()
    yield
    _reset_for_tests()
    # 还原现有快照（如果之前业务侧注册过）
    for name, cls in snapshot.items():
        register(name)(cls)


# 在 fixture 之后注册测试用 schema
def _seed_test_schemas():
    class FooConfig(BaseModel):
        """测试用 Foo 配置"""
        name: str = Field(..., description="名字")
        retries: int = Field(3, ge=0, le=10)

    class BarConfig(BaseModel):
        url: str

    register("test.foo")(FooConfig)
    register("test.bar")(BarConfig)
    return FooConfig, BarConfig


# ── 鉴权 ──────────────────────────────────────────────────


async def test_schemas_requires_auth(client: AsyncClient):
    r = await client.get("/v1/admin/schemas")
    assert r.status_code == 401


# ── 列表 ──────────────────────────────────────────────────


async def test_schemas_list(client: AsyncClient, admin_token: str):
    _seed_test_schemas()
    r = await client.get(
        "/v1/admin/schemas",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    names = [it["name"] for it in body["data"]]
    assert "test.foo" in names
    assert "test.bar" in names
    foo = next(it for it in body["data"] if it["name"] == "test.foo")
    assert foo["title"] == "测试用 Foo 配置"
    assert foo["qualified_name"].endswith("FooConfig")


async def test_schemas_list_prefix_filter(client: AsyncClient, admin_token: str):
    _seed_test_schemas()
    # 加一个非 test.* 前缀的
    class Other(BaseModel):
        a: int
    register("other.x")(Other)

    r = await client.get(
        "/v1/admin/schemas?prefix=test.",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    names = [it["name"] for it in r.json()["data"]]
    assert all(n.startswith("test.") for n in names)
    assert "other.x" not in names


# ── 详情 ──────────────────────────────────────────────────


async def test_schemas_detail_hit(client: AsyncClient, admin_token: str):
    _seed_test_schemas()
    r = await client.get(
        "/v1/admin/schemas/test.foo",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    schema = r.json()["data"]
    assert schema["type"] == "object"
    assert "name" in schema["properties"]
    assert schema["properties"]["retries"]["minimum"] == 0


async def test_schemas_detail_miss(client: AsyncClient, admin_token: str):
    r = await client.get(
        "/v1/admin/schemas/not.exist",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    # AgentNotFound 业务码经全局 handler 映射到 HTTP 404
    assert r.status_code == 404
    body = r.json()
    assert body["success"] is False
    assert "不存在" in body["message"]


async def test_schemas_detail_inline_refs(client: AsyncClient, admin_token: str):
    class Inner(BaseModel):
        v: int

    class WithNested(BaseModel):
        inner: Inner

    register("test.nested")(WithNested)

    r = await client.get(
        "/v1/admin/schemas/test.nested?inline_refs=true",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    schema = r.json()["data"]
    assert "$defs" not in schema
    # inner 直接展开成子 schema
    assert schema["properties"]["inner"]["type"] == "object"
    assert "v" in schema["properties"]["inner"]["properties"]
