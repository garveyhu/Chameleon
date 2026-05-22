"""P17.A1.1 channels admin API E2E

覆盖：
- 鉴权 401
- 列表（含 backfill 出的 default channels）+ provider_id 过滤
- 详情 hit / miss
- 创建（含明文 key 加密落盘）
- 更新（name / api_key / base_url / status / weight / priority）
- 状态机：auto_disabled → enabled 时 fail_count 自动归零
- 软删
"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import Channel, Provider, Role, User, UserRole
from chameleon.core.models.channel import ChannelStatus
from chameleon.core.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-channels-{rand}"
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
async def tmp_provider():
    """临时 provider，测试完物理删（含其 default channel backfill）"""
    code = f"e2e-prov-{secrets.token_hex(3)}"
    async with AsyncSessionLocal() as s:
        p = Provider(
            code=code,
            kind="llm",
            name="E2E Provider",
            base_url="https://example.com/v1",
            enabled=True,
        )
        s.add(p)
        await s.flush()
        pid = p.id
        await s.commit()
    yield pid
    async with AsyncSessionLocal() as s:
        await s.execute(delete(Channel).where(Channel.provider_id == pid))
        await s.execute(delete(Provider).where(Provider.id == pid))
        await s.commit()


# ── 鉴权 ─────────────────────────────────────────────────


async def test_channels_requires_auth(client: AsyncClient):
    r = await client.get("/v1/admin/channels")
    assert r.status_code == 401


# ── 列表 + 过滤 ───────────────────────────────────────────


async def test_channels_list_works(
    client: AsyncClient, admin_token: str, tmp_provider: int
):
    """通过 fixture 创建 channel 后列表能列出（不依赖 backfill 残留数据）"""
    # tmp_provider fixture 触发后表里至少有它的 provider，但 channels 表可能空。
    # 先建一条
    await client.post(
        "/v1/admin/channels",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"provider_id": tmp_provider, "name": "list-test"},
    )

    r = await client.get(
        "/v1/admin/channels",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    items = r.json()["data"]
    assert len(items) >= 1
    assert any(it["name"] == "list-test" for it in items)
    assert all("provider_code" in it for it in items)


async def test_channels_list_filter_by_provider(
    client: AsyncClient, admin_token: str, tmp_provider: int
):
    r = await client.get(
        f"/v1/admin/channels?provider_id={tmp_provider}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    items = r.json()["data"]
    assert all(it["provider_id"] == tmp_provider for it in items)


# ── CRUD ─────────────────────────────────────────────────


async def test_create_channel_encrypts_api_key(
    client: AsyncClient, admin_token: str, tmp_provider: int
):
    r = await client.post(
        "/v1/admin/channels",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "provider_id": tmp_provider,
            "name": "primary",
            "api_key": "sk-secret-test-key",
            "base_url": "https://override.example.com/v1",
            "weight": 5,
            "priority": 10,
        },
    )
    assert r.status_code == 200, r.text
    ch = r.json()["data"]
    assert ch["name"] == "primary"
    assert ch["has_api_key"] is True  # 不返明文，只暴露布尔
    assert "api_key" not in ch
    assert ch["base_url"] == "https://override.example.com/v1"
    assert ch["weight"] == 5
    assert ch["priority"] == 10
    assert ch["status"] == "enabled"

    # 数据库里 api_key 是密文（不是明文）
    async with AsyncSessionLocal() as s:
        row = (
            await s.execute(select(Channel).where(Channel.id == ch["id"]))
        ).scalar_one()
        assert row.api_key_encrypted is not None
        assert row.api_key_encrypted != "sk-secret-test-key"


async def test_create_channel_bad_provider(
    client: AsyncClient, admin_token: str
):
    r = await client.post(
        "/v1/admin/channels",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"provider_id": 999999999, "name": "bad", "api_key": "x"},
    )
    body = r.json()
    assert body["success"] is False
    assert "不存在" in body["message"]


async def test_update_channel_partial(
    client: AsyncClient, admin_token: str, tmp_provider: int
):
    # 先 create
    cr = await client.post(
        "/v1/admin/channels",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"provider_id": tmp_provider, "name": "p"},
    )
    cid = cr.json()["data"]["id"]

    # 只改 priority
    r = await client.post(
        f"/v1/admin/channels/{cid}/update",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"priority": 99},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["priority"] == 99


async def test_update_clears_api_key_with_empty_string(
    client: AsyncClient, admin_token: str, tmp_provider: int
):
    cr = await client.post(
        "/v1/admin/channels",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"provider_id": tmp_provider, "name": "p", "api_key": "init"},
    )
    cid = cr.json()["data"]["id"]
    assert cr.json()["data"]["has_api_key"] is True

    # 空字符串 → 清空
    r = await client.post(
        f"/v1/admin/channels/{cid}/update",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"api_key": ""},
    )
    assert r.json()["data"]["has_api_key"] is False


async def test_status_recovery_resets_fail_count(
    client: AsyncClient, admin_token: str, tmp_provider: int
):
    """auto_disabled → enabled 时 fail_count 自动归零（人工恢复语义）"""
    cr = await client.post(
        "/v1/admin/channels",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"provider_id": tmp_provider, "name": "p"},
    )
    cid = cr.json()["data"]["id"]

    # 直接 DB 设成 auto_disabled + fail_count=5
    async with AsyncSessionLocal() as s:
        ch = (
            await s.execute(select(Channel).where(Channel.id == cid))
        ).scalar_one()
        ch.status = ChannelStatus.AUTO_DISABLED.value
        ch.fail_count = 5
        await s.commit()

    # 通过 API 切回 enabled
    r = await client.post(
        f"/v1/admin/channels/{cid}/update",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "enabled"},
    )
    assert r.status_code == 200, r.text
    item = r.json()["data"]
    assert item["status"] == "enabled"
    assert item["fail_count"] == 0


async def test_update_invalid_status(
    client: AsyncClient, admin_token: str, tmp_provider: int
):
    cr = await client.post(
        "/v1/admin/channels",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"provider_id": tmp_provider, "name": "p"},
    )
    cid = cr.json()["data"]["id"]
    r = await client.post(
        f"/v1/admin/channels/{cid}/update",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "frobnicated"},
    )
    body = r.json()
    assert body["success"] is False
    assert "status 非法" in body["message"]


async def test_channel_health_endpoint(
    client: AsyncClient, admin_token: str, tmp_provider: int
):
    """P17.A2 健康端点 —— 实时返 channel 当前 fail_count / EWMA 延迟等"""
    cr = await client.post(
        "/v1/admin/channels",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"provider_id": tmp_provider, "name": "health-test"},
    )
    cid = cr.json()["data"]["id"]

    r = await client.get(
        f"/v1/admin/channels/{cid}/health",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    h = r.json()["data"]
    assert h["channel_id"] == cid
    assert h["status"] == "enabled"
    assert h["fail_count"] == 0
    assert h["response_time_ms"] is None
    assert h["last_success_at"] is None
    assert h["used_quota"] == 0


async def test_delete_channel_soft(
    client: AsyncClient, admin_token: str, tmp_provider: int
):
    cr = await client.post(
        "/v1/admin/channels",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"provider_id": tmp_provider, "name": "p"},
    )
    cid = cr.json()["data"]["id"]

    r = await client.post(
        f"/v1/admin/channels/{cid}/delete",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200

    # 列表里不再可见
    list_r = await client.get(
        f"/v1/admin/channels?provider_id={tmp_provider}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert cid not in [it["id"] for it in list_r.json()["data"]]

    # 详情走 404
    detail_r = await client.get(
        f"/v1/admin/channels/{cid}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert detail_r.status_code == 404
