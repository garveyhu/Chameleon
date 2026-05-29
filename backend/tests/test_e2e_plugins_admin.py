"""P19.2 PR #34: /v1/admin/plugins E2E（list/install/enable/disable/reload/uninstall/config）"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import PluginInstance, Role, User, UserRole
from chameleon.data.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-pl-{rand}"
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


@pytest_asyncio.fixture(autouse=True)
async def _clean_external_plugins():
    """每个测试后清掉非 builtin 插件，避免相互污染"""
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(
            delete(PluginInstance).where(PluginInstance.source != "builtin")
        )
        await s.commit()


def _hdr(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


# ── 鉴权 ─────────────────────────────────────────


async def test_plugins_requires_auth(client: AsyncClient):
    r = await client.get("/v1/admin/plugins")
    assert r.status_code == 401


# ── 列表 + builtin 可见 ──────────────────────────


async def test_list_includes_builtin(client: AsyncClient, admin_token: str):
    r = await client.get("/v1/admin/plugins", headers=_hdr(admin_token))
    assert r.status_code == 200
    items = r.json()["data"]
    keys = {i["plugin_key"] for i in items}
    assert {"local", "dify", "fastgpt"} <= keys
    builtins = [i for i in items if i["source"] == "builtin"]
    assert all(b["enabled"] for b in builtins)


# ── install 路径 ──────────────────────────────────


def _valid_manifest(name: str | None = None) -> dict:
    return {
        "name": name or f"test-plugin-{secrets.token_hex(2)}",
        "version": "1.0.0",
        "type": "tool",
        "entrypoint": "datetime:datetime",
        "chameleon_version": ">=0.5",
    }


async def test_install_then_get(client: AsyncClient, admin_token: str):
    manifest = _valid_manifest()
    r = await client.post(
        "/v1/admin/plugins/install",
        headers=_hdr(admin_token),
        json={"manifest": manifest, "source": "local"},
    )
    assert r.status_code == 200, r.text
    item = r.json()["data"]
    assert item["plugin_key"] == manifest["name"]
    assert item["enabled"] is True

    # GET 详情
    detail = await client.get(
        f"/v1/admin/plugins/{item['id']}", headers=_hdr(admin_token)
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["plugin_key"] == manifest["name"]


async def test_install_rejects_internal_entrypoint(
    client: AsyncClient, admin_token: str
):
    manifest = _valid_manifest()
    manifest["entrypoint"] = "chameleon.data.models.user:User"
    r = await client.post(
        "/v1/admin/plugins/install",
        headers=_hdr(admin_token),
        json={"manifest": manifest, "source": "local"},
    )
    assert r.status_code in (400, 500)
    assert r.json()["success"] is False
    assert "沙箱" in r.json()["message"] or "内部" in r.json()["message"]


async def test_install_rejects_bad_manifest(
    client: AsyncClient, admin_token: str
):
    r = await client.post(
        "/v1/admin/plugins/install",
        headers=_hdr(admin_token),
        json={
            "manifest": {"name": "x", "version": "latest", "type": "tool", "entrypoint": "x.y:Z"},
            "source": "local",
        },
    )
    assert r.status_code in (400, 500)
    assert r.json()["success"] is False


async def test_install_duplicate_rejected(
    client: AsyncClient, admin_token: str
):
    manifest = _valid_manifest()
    r1 = await client.post(
        "/v1/admin/plugins/install",
        headers=_hdr(admin_token),
        json={"manifest": manifest, "source": "local"},
    )
    assert r1.status_code == 200
    r2 = await client.post(
        "/v1/admin/plugins/install",
        headers=_hdr(admin_token),
        json={"manifest": manifest, "source": "local"},
    )
    assert r2.status_code in (400, 500)


# ── enable / disable / reload ───────────────────


async def test_disable_then_enable(client: AsyncClient, admin_token: str):
    manifest = _valid_manifest()
    r = await client.post(
        "/v1/admin/plugins/install",
        headers=_hdr(admin_token),
        json={"manifest": manifest, "source": "local"},
    )
    pid = r.json()["data"]["id"]

    dr = await client.post(
        f"/v1/admin/plugins/{pid}/disable", headers=_hdr(admin_token)
    )
    assert dr.status_code == 200
    assert dr.json()["data"]["enabled"] is False

    er = await client.post(
        f"/v1/admin/plugins/{pid}/enable", headers=_hdr(admin_token)
    )
    assert er.status_code == 200
    assert er.json()["data"]["enabled"] is True
    assert er.json()["data"]["loaded"] is True


async def test_reload(client: AsyncClient, admin_token: str):
    manifest = _valid_manifest()
    r = await client.post(
        "/v1/admin/plugins/install",
        headers=_hdr(admin_token),
        json={"manifest": manifest, "source": "local"},
    )
    pid = r.json()["data"]["id"]

    rr = await client.post(
        f"/v1/admin/plugins/{pid}/reload", headers=_hdr(admin_token)
    )
    assert rr.status_code == 200
    assert rr.json()["data"]["loaded"] is True


# ── uninstall ───────────────────────────────────


async def test_uninstall_external_succeeds(client: AsyncClient, admin_token: str):
    manifest = _valid_manifest()
    r = await client.post(
        "/v1/admin/plugins/install",
        headers=_hdr(admin_token),
        json={"manifest": manifest, "source": "local"},
    )
    pid = r.json()["data"]["id"]

    ur = await client.post(
        f"/v1/admin/plugins/{pid}/uninstall", headers=_hdr(admin_token)
    )
    assert ur.status_code == 200

    # 列表已不见
    lr = await client.get("/v1/admin/plugins", headers=_hdr(admin_token))
    keys = {i["plugin_key"] for i in lr.json()["data"]}
    assert manifest["name"] not in keys


async def test_uninstall_builtin_rejected(client: AsyncClient, admin_token: str):
    # 找 local builtin
    lr = await client.get("/v1/admin/plugins", headers=_hdr(admin_token))
    local = next(i for i in lr.json()["data"] if i["plugin_key"] == "local")

    r = await client.post(
        f"/v1/admin/plugins/{local['id']}/uninstall", headers=_hdr(admin_token)
    )
    assert r.status_code in (400, 500)
    assert r.json()["success"] is False
    assert "builtin" in r.json()["message"].lower()


# ── disable builtin → provider 实际下架 ─────────


async def test_disable_builtin_removes_provider_from_registry(
    client: AsyncClient, admin_token: str
):
    """关键回归：disable builtin 后 PROVIDERS dict 应不含该 key（不重启进程）"""
    from chameleon.providers.base import PROVIDERS

    lr = await client.get("/v1/admin/plugins", headers=_hdr(admin_token))
    fastgpt = next(i for i in lr.json()["data"] if i["plugin_key"] == "fastgpt")

    dr = await client.post(
        f"/v1/admin/plugins/{fastgpt['id']}/disable", headers=_hdr(admin_token)
    )
    assert dr.status_code == 200

    try:
        assert "fastgpt" not in PROVIDERS
    finally:
        # 还原，防影响其他测试
        await client.post(
            f"/v1/admin/plugins/{fastgpt['id']}/enable", headers=_hdr(admin_token)
        )


# ── update_config ──────────────────────────────


async def test_update_config(client: AsyncClient, admin_token: str):
    manifest = _valid_manifest()
    r = await client.post(
        "/v1/admin/plugins/install",
        headers=_hdr(admin_token),
        json={"manifest": manifest, "source": "local"},
    )
    pid = r.json()["data"]["id"]

    cr = await client.post(
        f"/v1/admin/plugins/{pid}/config",
        headers=_hdr(admin_token),
        json={"config": {"api_key": "secret", "debug": True}},
    )
    assert cr.status_code == 200
    assert cr.json()["data"]["config"] == {"api_key": "secret", "debug": True}
