"""P4 seed + 配置加密 + 导出/导入 测试

注：本测试会清空 DB 后再 seed，需独立运行 / 受 fixture 控制。
"""

from __future__ import annotations

import io
import zipfile

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from chameleon.data.infra.db import AsyncSessionLocal, engine
from chameleon.data.models import (
    Agent,
    ApiKey,
    Permission,
    Provider,
    Role,
    User,
)
from chameleon.data.utils.crypto import decrypt, encrypt
from chameleon.system.seed.defaults import all_permissions
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def empty_db():
    """清空 seed 相关业务表 → 让 run_seed_if_empty 走 seed 分支"""
    async with engine.begin() as conn:
        for tbl in (
            "user_roles",
            "role_permissions",
            "api_keys",
            "embed_configs",
            "models",
        ):
            await conn.execute(text(f"DELETE FROM {tbl}"))
        await conn.execute(text("DELETE FROM agents"))
        await conn.execute(text("DELETE FROM providers"))
        await conn.execute(text("DELETE FROM users"))
        await conn.execute(text("DELETE FROM roles"))
        await conn.execute(text("DELETE FROM permissions"))
    yield


# ── seed 流程 ──────────────────────────────────────────────


async def test_seed_creates_full_rbac(empty_db):
    creds = await run_seed_if_empty()
    assert creds is not None
    assert creds.username == "admin"
    assert len(creds.plaintext_password) >= 16

    async with AsyncSessionLocal() as s:
        # 权限点齐
        perm_count = (
            await s.execute(select(Permission))
        ).scalars().all()
        assert len(perm_count) == len(all_permissions())

        # 角色 + admin 拥有全部 permission
        admin_role = (
            await s.execute(
                select(Role)
                .where(Role.code == "admin")
                .options(selectinload(Role.permissions))
            )
        ).scalar_one()
        assert {p.code for p in admin_role.permissions} == {
            p[0] for p in all_permissions()
        }

        # 默认 admin user + must_change_password
        admin_user = (
            await s.execute(
                select(User)
                .where(User.username == "admin")
                .options(selectinload(User.roles))
            )
        ).scalar_one()
        assert admin_user.must_change_password is True
        assert "admin" in {r.code for r in admin_user.roles}


async def test_seed_idempotent(empty_db):
    """连续两次 seed：第二次返回 None（DB 已有数据跳过）"""
    creds1 = await run_seed_if_empty()
    assert creds1 is not None

    creds2 = await run_seed_if_empty()
    assert creds2 is None  # 已有 data 跳过


async def test_seed_providers_from_model_json(empty_db):
    await run_seed_if_empty()
    async with AsyncSessionLocal() as s:
        providers = (await s.execute(select(Provider))).scalars().all()
        codes = {p.code for p in providers}
        # config/model.json 里有 openai / deepseek / qwen
        assert {"openai", "deepseek", "qwen"} <= codes

        # qwen 的 api_key 加密了
        qwen = next(p for p in providers if p.code == "qwen")
        assert qwen.api_key_encrypted
        plaintext = decrypt(qwen.api_key_encrypted)
        assert plaintext.startswith("sk-")


async def test_seed_local_agents(empty_db):
    await run_seed_if_empty()
    async with AsyncSessionLocal() as s:
        agents = (
            await s.execute(select(Agent).where(Agent.source == "local"))
        ).scalars().all()
        keys = {a.agent_key for a in agents}
        # 至少这些本地 agent 应在表里
        assert "qwen-chat" in keys
        assert "example-echo-langgraph" in keys
        assert "example-echo-runnable" in keys
        assert "example-echo-native" in keys


# ── crypto 字段往返 ────────────────────────────────────────


async def test_provider_api_key_encrypt_roundtrip(empty_db):
    await run_seed_if_empty()
    async with AsyncSessionLocal() as s:
        # 改 qwen 的 api_key 走 service-like 流程
        qwen = (
            await s.execute(select(Provider).where(Provider.code == "qwen"))
        ).scalar_one()
        new_plain = "sk-rotated-1234567890abcdef"
        qwen.api_key_encrypted = encrypt(new_plain)
        await s.commit()

    async with AsyncSessionLocal() as s:
        qwen = (
            await s.execute(select(Provider).where(Provider.code == "qwen"))
        ).scalar_one()
        assert qwen.api_key_encrypted != new_plain  # 真的加密了
        assert decrypt(qwen.api_key_encrypted) == new_plain


# ── 导出 / 导入 ─────────────────────────────────────────────


async def test_export_zip_structure(client: AsyncClient, empty_db):
    """seed → 用 admin 登录 → 调 export → 验 zip 结构"""
    creds = await run_seed_if_empty()
    assert creds is not None

    # 登录拿 token
    r = await client.post(
        "/v1/auth/login",
        json={"username": creds.username, "password": creds.plaintext_password},
    )
    assert r.status_code == 200, r.text
    token = r.json()["data"]["access_token"]

    # 导出
    r = await client.post(
        "/v1/admin/settings/export-json",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"

    zip_bytes = r.content
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = set(zf.namelist())
    assert names == {
        "model.json",
        "agents.yaml",
        "users.json",
        "api_keys.json",
        "embed_configs.json",
        "README.md",
    }


async def test_export_then_import_roundtrip(client: AsyncClient, empty_db):
    """seed → 导出 → drop 业务数据 → 导入 → 验 user / api_key 还原"""
    creds = await run_seed_if_empty()
    r = await client.post(
        "/v1/auth/login",
        json={"username": creds.username, "password": creds.plaintext_password},
    )
    token = r.json()["data"]["access_token"]

    # 加一个 api_key（让导出有内容；app_id 为自由来源标签）
    test_hash = "export-test-hash"
    async with AsyncSessionLocal() as s:
        s.add(
            ApiKey(
                app_id="export-test-app",
                name="export test key",
                key_hash=test_hash,
                key_prefix="chm_exptst",
                scopes=[],
                scope_type="global",
            )
        )
        await s.commit()

    # 导出
    r = await client.post(
        "/v1/admin/settings/export-json",
        headers={"Authorization": f"Bearer {token}"},
    )
    zip_bytes = r.content

    # 清掉业务数据（保留 permission / role 让 import 能找到）
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM api_keys"))
        await conn.execute(text("DELETE FROM user_roles"))
        await conn.execute(text("DELETE FROM users"))

    # 重新登录用不了 → 用临时方法：直接复用 token？token 已废（user 没了）
    # → 重新 seed 一个临时 admin
    creds2 = await run_seed_if_empty()
    r2 = await client.post(
        "/v1/auth/login",
        json={"username": creds2.username, "password": creds2.plaintext_password},
    )
    token2 = r2.json()["data"]["access_token"]

    # 导入
    r3 = await client.post(
        "/v1/admin/settings/import-json",
        headers={"Authorization": f"Bearer {token2}"},
        data={"confirm": "true"},
        files={"file": ("backup.zip", zip_bytes, "application/zip")},
    )
    assert r3.status_code == 200, r3.text
    summary = r3.json()["data"]
    assert summary["api_keys_upserted"] >= 1
    assert summary["users_upserted"] >= 1

    # 验证 export-test-app 的 api_key 又回来了
    async with AsyncSessionLocal() as s:
        rows = (
            await s.execute(select(ApiKey).where(ApiKey.key_hash == test_hash))
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].app_id == "export-test-app"


async def test_import_requires_confirm(client: AsyncClient, empty_db):
    creds = await run_seed_if_empty()
    r = await client.post(
        "/v1/auth/login",
        json={"username": creds.username, "password": creds.plaintext_password},
    )
    token = r.json()["data"]["access_token"]

    # 构造一个空 zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("README.md", "fake")

    r = await client.post(
        "/v1/admin/settings/import-json",
        headers={"Authorization": f"Bearer {token}"},
        data={"confirm": "false"},  # 缺 confirm
        files={"file": ("x.zip", buf.getvalue(), "application/zip")},
    )
    assert r.status_code == 400
    assert r.json()["code"] == 40001  # ValidationError
