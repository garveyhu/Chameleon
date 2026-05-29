"""P3 鉴权 / 权限 E2E 测试

覆盖：
- 登录成功 / 失败 / 限流
- token 解析 / cookie set
- refresh 旋转 + 旧 jti 黑名单
- logout 黑名单
- 改密 → password_version 让旧 refresh 失效
- get_current_user / require_role / require_permission
- 异常账号（disabled / 不存在）
"""

from __future__ import annotations

import secrets

import pytest
import pytest_asyncio
from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from chameleon.core.api.response import Result
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.infra.redis import get_redis
from chameleon.data.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from chameleon.data.utils.passwords import hash_password
from chameleon.system.auth.dependencies import (
    CurrentUser,
    get_current_user,
    require_permission,
    require_role,
)
from chameleon.system.auth.rate_limit import MAX_ATTEMPTS

# ── fixture：建测试用户 + 角色 + 权限 ───────────────────────


@pytest_asyncio.fixture
async def test_user_factory():
    """返工厂函数；测试后清理"""
    created: list[tuple[str, str]] = []  # (username, role_code)

    async def factory(
        *,
        password: str = "TestPwd123!",
        roles: list[str] | None = None,
        permissions: list[str] | None = None,
        status: str = "active",
        must_change: bool = False,
    ):
        rand = secrets.token_hex(3)
        username = f"e2e-user-{rand}"
        role_code = f"e2e-role-{rand}"
        async with AsyncSessionLocal() as s:
            # 权限
            perm_rows = []
            for code in permissions or []:
                p = Permission(
                    code=code,
                    resource=code.split(":")[0],
                    action=code.split(":")[1] if ":" in code else "read",
                )
                s.add(p)
                perm_rows.append(p)

            # 角色
            role = Role(code=role_code, name=role_code)
            s.add(role)
            await s.flush()

            for p in perm_rows:
                s.add(RolePermission(role_id=role.id, permission_id=p.id))

            # 用户
            user = User(
                username=username,
                password_hash=hash_password(password),
                status=status,
                must_change_password=must_change,
            )
            s.add(user)
            await s.flush()
            s.add(UserRole(user_id=user.id, role_id=role.id))
            await s.commit()
            user_id = user.id
        created.append((username, role_code))
        return {
            "username": username,
            "password": password,
            "user_id": user_id,
            "role_code": role_code,
        }

    yield factory

    # cleanup
    async with AsyncSessionLocal() as s:
        for username, role_code in created:
            await s.execute(delete(User).where(User.username == username))
            await s.execute(delete(Role).where(Role.code == role_code))
        await s.execute(delete(Permission).where(Permission.code.like("e2e-%")))
        await s.execute(delete(Permission).where(Permission.code.like("agents:%")))
        await s.execute(delete(Permission).where(Permission.code.like("users:%")))
        await s.commit()


@pytest_asyncio.fixture
async def _clear_redis_rate():
    """每个测试清掉登录限流计数（同 IP 复用导致计数累积）"""
    yield
    client = get_redis()
    # 清所有 e2e 测试 IP 的计数
    cursor = 0
    while True:
        cursor, keys = await client.scan(cursor, match="chameleon:login_attempts:*", count=100)
        if keys:
            await client.delete(*keys)
        if cursor == 0:
            break


# ── 登录 ────────────────────────────────────────────────────


@pytest.mark.usefixtures("_clear_redis_rate")
async def test_login_success(client: AsyncClient, test_user_factory):
    u = await test_user_factory()
    r = await client.post(
        "/v1/auth/login",
        json={"username": u["username"], "password": u["password"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"]
    assert body["data"]["access_token"]
    assert body["data"]["token_type"] == "Bearer"
    assert body["data"]["expires_in"] > 0
    # refresh cookie 已 set
    assert "chameleon_refresh" in r.cookies


@pytest.mark.usefixtures("_clear_redis_rate")
async def test_login_wrong_password(client: AsyncClient, test_user_factory):
    u = await test_user_factory()
    r = await client.post(
        "/v1/auth/login",
        json={"username": u["username"], "password": "wrong"},
    )
    assert r.status_code == 401
    body = r.json()
    assert body["code"] == 40114  # LoginFailed


@pytest.mark.usefixtures("_clear_redis_rate")
async def test_login_user_not_exists(client: AsyncClient):
    r = await client.post(
        "/v1/auth/login",
        json={"username": "nonexistent", "password": "any"},
    )
    assert r.status_code == 401
    assert r.json()["code"] == 40114


@pytest.mark.usefixtures("_clear_redis_rate")
async def test_login_account_disabled(client: AsyncClient, test_user_factory):
    u = await test_user_factory(status="disabled")
    r = await client.post(
        "/v1/auth/login",
        json={"username": u["username"], "password": u["password"]},
    )
    assert r.status_code == 401
    assert r.json()["code"] == 40115  # AccountDisabled


@pytest.mark.usefixtures("_clear_redis_rate")
async def test_login_rate_limit(client: AsyncClient, test_user_factory):
    u = await test_user_factory()
    # 连续 5 次错误密码
    for _ in range(MAX_ATTEMPTS):
        r = await client.post(
            "/v1/auth/login",
            json={"username": u["username"], "password": "wrong"},
        )
        assert r.status_code == 401
    # 第 6 次：限流
    r = await client.post(
        "/v1/auth/login",
        json={"username": u["username"], "password": u["password"]},
    )
    assert r.status_code == 401
    assert r.json()["code"] == 40116  # LoginRateLimit


# ── /me ───────────────────────────────────────────────────


@pytest.mark.usefixtures("_clear_redis_rate")
async def test_me_returns_roles_and_permissions(
    client: AsyncClient, test_user_factory
):
    u = await test_user_factory(permissions=["agents:read", "users:read"])
    # 登录拿 token
    r = await client.post(
        "/v1/auth/login",
        json={"username": u["username"], "password": u["password"]},
    )
    token = r.json()["data"]["access_token"]
    # 调 /me
    r = await client.get(
        "/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["username"] == u["username"]
    assert u["role_code"] in data["roles"]
    assert set(data["permissions"]) == {"agents:read", "users:read"}


async def test_me_missing_jwt(client: AsyncClient):
    r = await client.get("/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["code"] == 40110  # JwtMissing


async def test_me_invalid_jwt(client: AsyncClient):
    r = await client.get(
        "/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert r.status_code == 401
    assert r.json()["code"] in (40112,)  # JwtInvalid


# ── refresh ───────────────────────────────────────────────


@pytest.mark.usefixtures("_clear_redis_rate")
async def test_refresh_rotates_token(client: AsyncClient, test_user_factory):
    u = await test_user_factory()
    r = await client.post(
        "/v1/auth/login",
        json={"username": u["username"], "password": u["password"]},
    )
    old_cookie = r.cookies.get("chameleon_refresh")
    assert old_cookie

    # 用 cookie 拿新 token
    r2 = await client.post("/v1/auth/refresh", cookies={"chameleon_refresh": old_cookie})
    assert r2.status_code == 200
    new_cookie = r2.cookies.get("chameleon_refresh")
    assert new_cookie
    assert new_cookie != old_cookie  # 旋转

    # 旧 refresh 已被吊销
    r3 = await client.post("/v1/auth/refresh", cookies={"chameleon_refresh": old_cookie})
    assert r3.status_code == 401
    assert r3.json()["code"] == 40113  # RefreshTokenInvalid


async def test_refresh_without_cookie(client: AsyncClient):
    r = await client.post("/v1/auth/refresh")
    assert r.status_code == 401
    assert r.json()["code"] == 40113


# ── logout ────────────────────────────────────────────────


@pytest.mark.usefixtures("_clear_redis_rate")
async def test_logout_blacklists_access(client: AsyncClient, test_user_factory):
    u = await test_user_factory()
    r = await client.post(
        "/v1/auth/login",
        json={"username": u["username"], "password": u["password"]},
    )
    token = r.json()["data"]["access_token"]
    refresh = r.cookies.get("chameleon_refresh")

    # logout
    r2 = await client.post(
        "/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
        cookies={"chameleon_refresh": refresh} if refresh else None,
    )
    assert r2.status_code == 200

    # access 已黑名单
    r3 = await client.get(
        "/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert r3.status_code == 401
    assert r3.json()["code"] == 40112  # JwtInvalid


# ── change_password ──────────────────────────────────────


@pytest.mark.usefixtures("_clear_redis_rate")
async def test_change_password_invalidates_old_refresh(
    client: AsyncClient, test_user_factory
):
    u = await test_user_factory()
    r = await client.post(
        "/v1/auth/login",
        json={"username": u["username"], "password": u["password"]},
    )
    token = r.json()["data"]["access_token"]
    old_refresh = r.cookies.get("chameleon_refresh")

    # 改密
    r2 = await client.post(
        "/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        cookies={"chameleon_refresh": old_refresh} if old_refresh else None,
        json={"old_password": u["password"], "new_password": "NewPwd123!"},
    )
    assert r2.status_code == 200

    # 旧 refresh 已废
    r3 = await client.post(
        "/v1/auth/refresh", cookies={"chameleon_refresh": old_refresh}
    )
    assert r3.status_code == 401

    # 新密码登录可以
    r4 = await client.post(
        "/v1/auth/login",
        json={"username": u["username"], "password": "NewPwd123!"},
    )
    assert r4.status_code == 200


@pytest.mark.usefixtures("_clear_redis_rate")
async def test_change_password_wrong_old(client: AsyncClient, test_user_factory):
    u = await test_user_factory()
    r = await client.post(
        "/v1/auth/login",
        json={"username": u["username"], "password": u["password"]},
    )
    token = r.json()["data"]["access_token"]
    r2 = await client.post(
        "/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"old_password": "wrong", "new_password": "NewPwd123!"},
    )
    assert r2.status_code == 401
    assert r2.json()["code"] == 40114


# ── RBAC dependency ──────────────────────────────────────


def _add_test_rbac_router(app) -> None:
    """挂临时路由测 require_role / require_permission"""
    r = APIRouter(prefix="/v1/_rbac_test")

    @r.get("/whoami")
    async def whoami(u: CurrentUser = Depends(get_current_user)) -> Result[dict]:
        return Result.ok({"id": u.id, "username": u.username, "roles": u.roles})

    @r.get("/admin-only", dependencies=[Depends(require_role("admin"))])
    async def admin_only() -> Result[dict]:
        return Result.ok({"ok": True})

    @r.get(
        "/users-write",
        dependencies=[Depends(require_permission("users:write"))],
    )
    async def users_write() -> Result[dict]:
        return Result.ok({"ok": True})

    app.include_router(r)


@pytest_asyncio.fixture
async def rbac_client():
    """单独跑一个 FastAPI 实例，挂上 _rbac_test 路由"""
    from chameleon.app.main import create_app

    app: FastAPI = create_app()
    _add_test_rbac_router(app)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.mark.usefixtures("_clear_redis_rate")
async def test_require_role_pass(rbac_client: AsyncClient, test_user_factory):
    """require_role 同时接受多个；这里把 role_code 加进守卫的可接受集合"""
    u = await test_user_factory()

    # 临时挂个新路由，守卫接受用户的随机 role_code（不依赖内置 admin）
    from fastapi import APIRouter, Depends

    r_test = APIRouter(prefix="/v1/_rbac_dyn")

    @r_test.get(
        "/by-role",
        dependencies=[Depends(require_role(u["role_code"]))],
    )
    async def by_role() -> Result[dict]:
        return Result.ok({"ok": True})

    rbac_client._transport.app.include_router(r_test)  # type: ignore[attr-defined]

    r = await rbac_client.post(
        "/v1/auth/login",
        json={"username": u["username"], "password": u["password"]},
    )
    token = r.json()["data"]["access_token"]
    r2 = await rbac_client.get(
        "/v1/_rbac_dyn/by-role", headers={"Authorization": f"Bearer {token}"}
    )
    assert r2.status_code == 200


@pytest.mark.usefixtures("_clear_redis_rate")
async def test_require_role_deny(rbac_client: AsyncClient, test_user_factory):
    u = await test_user_factory()  # 默认角色非 admin
    r = await rbac_client.post(
        "/v1/auth/login",
        json={"username": u["username"], "password": u["password"]},
    )
    token = r.json()["data"]["access_token"]
    r2 = await rbac_client.get(
        "/v1/_rbac_test/admin-only", headers={"Authorization": f"Bearer {token}"}
    )
    assert r2.status_code == 403
    assert r2.json()["code"] == 40310


@pytest.mark.usefixtures("_clear_redis_rate")
async def test_require_permission_pass(rbac_client: AsyncClient, test_user_factory):
    u = await test_user_factory(permissions=["users:write"])
    r = await rbac_client.post(
        "/v1/auth/login",
        json={"username": u["username"], "password": u["password"]},
    )
    token = r.json()["data"]["access_token"]
    r2 = await rbac_client.get(
        "/v1/_rbac_test/users-write", headers={"Authorization": f"Bearer {token}"}
    )
    assert r2.status_code == 200


@pytest.mark.usefixtures("_clear_redis_rate")
async def test_require_permission_deny(
    rbac_client: AsyncClient, test_user_factory
):
    u = await test_user_factory(permissions=["users:read"])  # 只读不能写
    r = await rbac_client.post(
        "/v1/auth/login",
        json={"username": u["username"], "password": u["password"]},
    )
    token = r.json()["data"]["access_token"]
    r2 = await rbac_client.get(
        "/v1/_rbac_test/users-write", headers={"Authorization": f"Bearer {token}"}
    )
    assert r2.status_code == 403
    assert r2.json()["code"] == 40310
