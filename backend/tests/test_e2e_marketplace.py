"""P20.2 PR #49 E2E: marketplace registries + sync + search + install_from_remote"""

from __future__ import annotations

import json
import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import (
    PluginInstance,
    PluginRegistryEntry,
    Role,
    User,
    UserRole,
)
from chameleon.data.utils.passwords import hash_password
from chameleon.integrations.plugins.signing import generate_keypair, sign_manifest
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-mkt-{rand}"
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


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(
            delete(PluginInstance).where(PluginInstance.source == "marketplace")
        )
        await s.execute(delete(PluginRegistryEntry))
        await s.commit()


def _hdr(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


# ── registry CRUD ──────────────────────────────────────


async def test_registry_crud(client: AsyncClient, admin_token: str):
    # add
    r = await client.post(
        "/v1/admin/marketplace/registries",
        headers=_hdr(admin_token),
        json={
            "registry_url": "https://registry-a.example.test",
            "name": "Test Registry A",
        },
    )
    assert r.status_code == 200, r.text
    rid = r.json()["data"]["id"]

    # list
    lr = await client.get(
        "/v1/admin/marketplace/registries", headers=_hdr(admin_token)
    )
    assert any(reg["id"] == rid for reg in lr.json()["data"])

    # disable
    ur = await client.post(
        f"/v1/admin/marketplace/registries/{rid}/update",
        headers=_hdr(admin_token),
        json={"enabled": False},
    )
    assert ur.json()["data"]["enabled"] is False

    # delete
    dr = await client.post(
        f"/v1/admin/marketplace/registries/{rid}/delete",
        headers=_hdr(admin_token),
    )
    assert dr.status_code == 200


async def test_duplicate_registry_rejected(
    client: AsyncClient, admin_token: str
):
    url = f"https://dup-{secrets.token_hex(2)}.example.test"
    r1 = await client.post(
        "/v1/admin/marketplace/registries",
        headers=_hdr(admin_token),
        json={"registry_url": url, "name": "x"},
    )
    assert r1.status_code == 200
    r2 = await client.post(
        "/v1/admin/marketplace/registries",
        headers=_hdr(admin_token),
        json={"registry_url": url, "name": "y"},
    )
    assert r2.status_code in (400, 500)


# ── sync + install (mock registry + real signing) ─────


async def test_sync_and_install_with_valid_signature(
    client: AsyncClient,
    admin_token: str,
    respx_mock,
):
    """全链路：注册 → sync 拉远端 index → search 看到 → install 验签通过"""
    import httpx

    kp = generate_keypair()
    plugin_name = f"openrouter-{secrets.token_hex(2)}"
    manifest = {
        "name": plugin_name,
        "version": "1.0.0",
        "type": "tool",
        "entrypoint": "datetime:datetime",  # stdlib，install 时能 import
        "chameleon_version": ">=0.5",
        "description": "Marketplace test plugin",
    }
    manifest_bytes = json.dumps(manifest, separators=(",", ":")).encode()
    signature_b64 = sign_manifest(manifest_bytes, kp.private_key_b64)

    base = "https://registry-x.example.test"
    index = {
        "version": 1,
        "publishers": {"official": kp.public_key_pinning},
        "plugins": [
            {
                "name": plugin_name,
                "latest": "1.0.0",
                "type": "tool",
                "description": "Marketplace test plugin",
                "manifest_url": f"{base}/{plugin_name}/1.0.0/manifest.json",
                "signature_url": f"{base}/{plugin_name}/1.0.0/manifest.json.sig",
                "publisher": "official",
                "tags": ["test"],
                "downloads": 42,
                "updated_at": "2026-11-22T00:00:00Z",
            }
        ],
    }
    respx_mock.get(f"{base}/index.json").mock(
        return_value=httpx.Response(200, json=index)
    )
    respx_mock.get(f"{base}/{plugin_name}/1.0.0/manifest.json").mock(
        return_value=httpx.Response(200, content=manifest_bytes)
    )
    respx_mock.get(f"{base}/{plugin_name}/1.0.0/manifest.json.sig").mock(
        return_value=httpx.Response(200, content=signature_b64.encode())
    )

    # 1. 注册 registry
    ar = await client.post(
        "/v1/admin/marketplace/registries",
        headers=_hdr(admin_token),
        json={"registry_url": base, "name": "Test"},
    )
    rid = ar.json()["data"]["id"]

    # 2. sync
    sr = await client.post(
        f"/v1/admin/marketplace/registries/{rid}/sync",
        headers=_hdr(admin_token),
    )
    assert sr.status_code == 200, sr.text
    assert sr.json()["data"]["entries"] == 1
    assert sr.json()["data"]["publishers"] == 1

    # 3. search 看到
    se = await client.get(
        "/v1/admin/marketplace/search", headers=_hdr(admin_token)
    )
    found = [
        e for e in se.json()["data"] if e["name"] == plugin_name
    ]
    assert len(found) == 1
    assert found[0]["installed"] is False
    assert found[0]["publisher"] == "official"

    # 4. install
    ir = await client.post(
        "/v1/admin/marketplace/install",
        headers=_hdr(admin_token),
        json={"registry_id": rid, "plugin_name": plugin_name},
    )
    assert ir.status_code == 200, ir.text
    assert ir.json()["data"]["plugin_key"] == plugin_name
    assert ir.json()["data"]["registry"] == "Test"

    # 5. 再 search，installed=True
    se2 = await client.get(
        "/v1/admin/marketplace/search", headers=_hdr(admin_token)
    )
    found2 = [
        e for e in se2.json()["data"] if e["name"] == plugin_name
    ]
    assert found2[0]["installed"] is True


async def test_install_rejects_tampered_manifest(
    client: AsyncClient,
    admin_token: str,
    respx_mock,
):
    """attacker 改了 manifest 内容但用合法签名 —— 验签必拒"""
    import httpx

    kp = generate_keypair()
    plugin_name = f"evil-{secrets.token_hex(2)}"
    # 签的是原始 manifest
    original = {
        "name": plugin_name,
        "version": "1.0.0",
        "type": "tool",
        "entrypoint": "datetime:datetime",
        "chameleon_version": ">=0.5",
    }
    sig = sign_manifest(
        json.dumps(original, separators=(",", ":")).encode(),
        kp.private_key_b64,
    )
    # 但发出的是被改的 manifest（entrypoint 换了）
    tampered = {**original, "entrypoint": "os:system"}
    tampered_bytes = json.dumps(tampered, separators=(",", ":")).encode()

    base = f"https://tamper-{secrets.token_hex(2)}.example.test"
    respx_mock.get(f"{base}/index.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "version": 1,
                "publishers": {"official": kp.public_key_pinning},
                "plugins": [
                    {
                        "name": plugin_name,
                        "latest": "1.0.0",
                        "type": "tool",
                        "manifest_url": f"{base}/m.json",
                        "signature_url": f"{base}/m.sig",
                        "publisher": "official",
                        "tags": [],
                        "downloads": 0,
                        "updated_at": "",
                    }
                ],
            },
        )
    )
    respx_mock.get(f"{base}/m.json").mock(
        return_value=httpx.Response(200, content=tampered_bytes)
    )
    respx_mock.get(f"{base}/m.sig").mock(
        return_value=httpx.Response(200, content=sig.encode())
    )

    ar = await client.post(
        "/v1/admin/marketplace/registries",
        headers=_hdr(admin_token),
        json={"registry_url": base, "name": "tamper"},
    )
    rid = ar.json()["data"]["id"]
    await client.post(
        f"/v1/admin/marketplace/registries/{rid}/sync",
        headers=_hdr(admin_token),
    )
    ir = await client.post(
        "/v1/admin/marketplace/install",
        headers=_hdr(admin_token),
        json={"registry_id": rid, "plugin_name": plugin_name},
    )
    assert ir.status_code in (400, 500)
    assert "签名" in ir.json()["message"]


async def test_install_rejects_unknown_publisher(
    client: AsyncClient,
    admin_token: str,
    respx_mock,
):
    """index.plugins 里写了一个未出现在 publishers 的 publisher → entry 应被
    fetch_index drop 掉，search 查不到，install 报 404"""
    import httpx

    base = f"https://nopub-{secrets.token_hex(2)}.example.test"
    respx_mock.get(f"{base}/index.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "version": 1,
                "publishers": {},  # 空
                "plugins": [
                    {
                        "name": "ghost",
                        "latest": "1.0.0",
                        "type": "tool",
                        "manifest_url": "x",
                        "signature_url": "x",
                        "publisher": "phantom",
                        "tags": [],
                        "downloads": 0,
                        "updated_at": "",
                    }
                ],
            },
        )
    )
    ar = await client.post(
        "/v1/admin/marketplace/registries",
        headers=_hdr(admin_token),
        json={"registry_url": base, "name": "nopub"},
    )
    rid = ar.json()["data"]["id"]
    sr = await client.post(
        f"/v1/admin/marketplace/registries/{rid}/sync",
        headers=_hdr(admin_token),
    )
    # sync ok 但 entry 被 drop
    assert sr.status_code == 200
    assert sr.json()["data"]["entries"] == 0

    ir = await client.post(
        "/v1/admin/marketplace/install",
        headers=_hdr(admin_token),
        json={"registry_id": rid, "plugin_name": "ghost"},
    )
    assert ir.status_code in (400, 404, 500)
    assert "找不到" in ir.json()["message"] or "请先 sync" in ir.json()["message"]


async def test_install_rejects_when_registry_disabled(
    client: AsyncClient, admin_token: str
):
    base = f"https://dis-{secrets.token_hex(2)}.example.test"
    ar = await client.post(
        "/v1/admin/marketplace/registries",
        headers=_hdr(admin_token),
        json={"registry_url": base, "name": "dis"},
    )
    rid = ar.json()["data"]["id"]
    await client.post(
        f"/v1/admin/marketplace/registries/{rid}/update",
        headers=_hdr(admin_token),
        json={"enabled": False},
    )
    ir = await client.post(
        "/v1/admin/marketplace/install",
        headers=_hdr(admin_token),
        json={"registry_id": rid, "plugin_name": "x"},
    )
    assert ir.status_code in (400, 500)


async def test_search_filters_by_query(
    client: AsyncClient,
    admin_token: str,
    respx_mock,
):
    """search ?q= 过滤；不带 q 返全部"""
    import httpx

    kp = generate_keypair()
    base = f"https://q-{secrets.token_hex(2)}.example.test"
    plugins = [
        {
            "name": f"alpha-{secrets.token_hex(2)}",
            "latest": "1.0.0",
            "type": "tool",
            "description": "first plugin",
            "manifest_url": f"{base}/a/m.json",
            "signature_url": f"{base}/a/m.sig",
            "publisher": "official",
            "tags": ["alpha"],
            "downloads": 1,
            "updated_at": "",
        },
        {
            "name": f"beta-{secrets.token_hex(2)}",
            "latest": "1.0.0",
            "type": "provider",
            "description": "second plugin",
            "manifest_url": f"{base}/b/m.json",
            "signature_url": f"{base}/b/m.sig",
            "publisher": "official",
            "tags": ["beta"],
            "downloads": 2,
            "updated_at": "",
        },
    ]
    respx_mock.get(f"{base}/index.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "version": 1,
                "publishers": {"official": kp.public_key_pinning},
                "plugins": plugins,
            },
        )
    )
    ar = await client.post(
        "/v1/admin/marketplace/registries",
        headers=_hdr(admin_token),
        json={"registry_url": base, "name": "search-test"},
    )
    rid = ar.json()["data"]["id"]
    await client.post(
        f"/v1/admin/marketplace/registries/{rid}/sync",
        headers=_hdr(admin_token),
    )

    # 不带 q
    all_r = await client.get(
        "/v1/admin/marketplace/search", headers=_hdr(admin_token)
    )
    assert (
        len([e for e in all_r.json()["data"] if e["registry_id"] == rid])
        == 2
    )

    # 带 q=first → 只匹配 alpha
    f_r = await client.get(
        "/v1/admin/marketplace/search",
        headers=_hdr(admin_token),
        params={"q": "first"},
    )
    matched = [e for e in f_r.json()["data"] if e["registry_id"] == rid]
    assert len(matched) == 1
    assert "alpha" in matched[0]["name"]
