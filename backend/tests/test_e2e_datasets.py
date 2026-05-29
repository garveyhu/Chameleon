"""P18.3 PR #24 E2E：datasets CRUD + 一键采样 + 脱敏 + 人工标注"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import (
    CallLog,
    Dataset,
    DatasetItem,
    Role,
    User,
    UserRole,
)
from chameleon.data.utils.passwords import hash_password
from chameleon.system.api_key.service import record_call
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-ds-{rand}"
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


@pytest_asyncio.fixture
async def app_with_logs():
    """临时 app + 几条 trace 根 call_log，供采样"""
    suffix = secrets.token_hex(3)
    app_key = f"e2e-dsapp-{suffix}"

    async with AsyncSessionLocal() as s:
        for i in range(5):
            await record_call(
                s,
                request_id=f"rid-ds-{suffix}-{i}",
                app_id=app_key,
                agent_key="example",
                session_id=None,
                stream=False,
                success=True,
                code=200,
                error_message=None,
                duration_ms=120 + i,
                request_payload={
                    "user_input": f"敏感问题 #{i}：账户余额是多少？",
                    "context_id": i,
                },
                response_payload={"answer": f"回复 #{i}"},
                observation_type="trace",
            )
        await s.commit()
    yield {"app_key": app_key, "log_count": 5}

    async with AsyncSessionLocal() as s:
        # 清 call_logs + dataset_items 引用了它们的
        await s.execute(
            delete(DatasetItem).where(
                DatasetItem.source_call_log_id.like(f"rid-ds-{suffix}-%")
            )
        )
        await s.execute(delete(CallLog).where(CallLog.app_id == app_key))
        await s.commit()


@pytest_asyncio.fixture(autouse=True)
async def _clean_datasets():
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(delete(DatasetItem))
        await s.execute(delete(Dataset))
        await s.commit()


# ── 鉴权 ─────────────────────────────────────────────────


async def test_datasets_requires_auth(client: AsyncClient):
    r = await client.get("/v1/admin/datasets")
    assert r.status_code == 401


# ── CRUD ─────────────────────────────────────────────────


async def test_create_and_list_dataset(
    client: AsyncClient, admin_token: str
):
    r = await client.post(
        "/v1/admin/datasets",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "ds-1", "description": "试用"},
    )
    assert r.status_code == 200, r.text
    ds = r.json()["data"]
    assert ds["name"] == "ds-1"
    assert ds["item_count"] == 0

    list_r = await client.get(
        "/v1/admin/datasets",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert ds["id"] in [d["id"] for d in list_r.json()["data"]]


async def test_update_and_delete_dataset(
    client: AsyncClient, admin_token: str
):
    cr = await client.post(
        "/v1/admin/datasets",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "x"},
    )
    did = cr.json()["data"]["id"]

    ur = await client.post(
        f"/v1/admin/datasets/{did}/update",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "renamed"},
    )
    assert ur.json()["data"]["name"] == "renamed"

    dr = await client.post(
        f"/v1/admin/datasets/{did}/delete",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert dr.status_code == 200


# ── 采样 + 脱敏 ───────────────────────────────────────────


async def test_sample_from_logs_redacts_input(
    client: AsyncClient, admin_token: str, app_with_logs: dict
):
    cr = await client.post(
        "/v1/admin/datasets",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "sample-ds"},
    )
    did = cr.json()["data"]["id"]

    r = await client.post(
        f"/v1/admin/datasets/{did}/sample-from-logs",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"app_id": app_with_logs["app_key"], "limit": 10},
    )
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["added"] == app_with_logs["log_count"]
    assert result["skipped"] == 0

    # items list 验证脱敏
    items_r = await client.get(
        f"/v1/admin/datasets/{did}/items",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    items = items_r.json()["data"]
    assert len(items) == app_with_logs["log_count"]
    first = items[0]
    # _redacted 标记 + user_input 不是原始字符串
    assert first["input_payload"]["_redacted"] is True
    ui = first["input_payload"]["user_input"]
    assert "hash" in ui and ui["hash"].startswith("sha256:")
    assert ui["length"] > 0
    # preview 截断
    assert isinstance(ui["preview"], str)
    # 原始字符串不应该完整出现
    assert "账户余额是多少？" not in first["input_payload"].get(
        "raw_user_input", ""
    )

    # dataset item_count 自动累加
    ds_r = await client.get(
        f"/v1/admin/datasets/{did}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert ds_r.json()["data"]["item_count"] == app_with_logs["log_count"]


async def test_sample_pii_mask_in_preview(
    client: AsyncClient, admin_token: str
):
    """P21.1：preview 字段必须脱敏邮箱/手机/身份证"""
    suffix = secrets.token_hex(3)
    app_key = f"e2e-dspii-{suffix}"
    async with AsyncSessionLocal() as s:
        await record_call(
            s,
            request_id=f"rid-pii-{suffix}-0",
            app_id=app_key,
            agent_key="example",
            session_id=None,
            stream=False,
            success=True,
            code=200,
            error_message=None,
            duration_ms=100,
            request_payload={
                "user_input": "联系 alice@example.com 或 13812345678",
            },
            response_payload={"answer": "OK"},
            observation_type="trace",
        )
        await s.commit()
    try:
        cr = await client.post(
            "/v1/admin/datasets",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "pii-mask-ds"},
        )
        did = cr.json()["data"]["id"]

        r = await client.post(
            f"/v1/admin/datasets/{did}/sample-from-logs",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"app_id": app_key, "limit": 5, "pii_strategy": "mask"},
        )
        assert r.status_code == 200
        assert r.json()["data"]["added"] == 1
        assert r.json()["data"]["dropped_pii"] == 0

        items_r = await client.get(
            f"/v1/admin/datasets/{did}/items",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        items = items_r.json()["data"]
        preview = items[0]["input_payload"]["user_input"]["preview"]
        assert "<EMAIL>" in preview
        assert "<PHONE>" in preview
        assert "alice@example.com" not in preview
        assert "13812345678" not in preview
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(
                delete(DatasetItem).where(
                    DatasetItem.source_call_log_id.like(f"rid-pii-{suffix}-%")
                )
            )
            await s.execute(delete(CallLog).where(CallLog.app_id == app_key))
            await s.commit()


async def test_sample_pii_drop_strategy(
    client: AsyncClient, admin_token: str
):
    """P21.1：drop 策略下含 PII 的 call_log 整条跳过"""
    suffix = secrets.token_hex(3)
    app_key = f"e2e-dsdrop-{suffix}"
    async with AsyncSessionLocal() as s:
        # 一条有 PII，一条无 PII
        await record_call(
            s,
            request_id=f"rid-drop-{suffix}-pii",
            app_id=app_key,
            agent_key="example",
            session_id=None,
            stream=False,
            success=True,
            code=200,
            error_message=None,
            duration_ms=100,
            request_payload={"user_input": "邮箱 user@x.com"},
            response_payload={"answer": "OK"},
            observation_type="trace",
        )
        await record_call(
            s,
            request_id=f"rid-drop-{suffix}-clean",
            app_id=app_key,
            agent_key="example",
            session_id=None,
            stream=False,
            success=True,
            code=200,
            error_message=None,
            duration_ms=100,
            request_payload={"user_input": "什么是 RAG？"},
            response_payload={"answer": "OK"},
            observation_type="trace",
        )
        await s.commit()
    try:
        cr = await client.post(
            "/v1/admin/datasets",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "pii-drop-ds"},
        )
        did = cr.json()["data"]["id"]

        r = await client.post(
            f"/v1/admin/datasets/{did}/sample-from-logs",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"app_id": app_key, "limit": 5, "pii_strategy": "drop"},
        )
        data = r.json()["data"]
        assert data["added"] == 1
        assert data["dropped_pii"] == 1
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(
                delete(DatasetItem).where(
                    DatasetItem.source_call_log_id.like(f"rid-drop-{suffix}-%")
                )
            )
            await s.execute(delete(CallLog).where(CallLog.app_id == app_key))
            await s.commit()


async def test_bulk_import_basic(client: AsyncClient, admin_token: str):
    """P21.1：手工 bulk-import items（无 PII）"""
    cr = await client.post(
        "/v1/admin/datasets",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "bulk-ds"},
    )
    did = cr.json()["data"]["id"]
    r = await client.post(
        f"/v1/admin/datasets/{did}/items/bulk-import",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "items": [
                {
                    "input_payload": {"q": "什么是 RAG？"},
                    "expected_output": {"answer": "RAG 是检索增强生成"},
                },
                {
                    "input_payload": {"q": "什么是 Agent？"},
                    "expected_output": {"answer": "Agent 是自主智能体"},
                },
            ]
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["added"] == 2
    assert data["dropped_pii"] == 0


async def test_bulk_import_pii_drop(client: AsyncClient, admin_token: str):
    """P21.1：bulk-import 配 drop 策略，含 PII 的整条跳过"""
    cr = await client.post(
        "/v1/admin/datasets",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "bulk-drop-ds"},
    )
    did = cr.json()["data"]["id"]
    r = await client.post(
        f"/v1/admin/datasets/{did}/items/bulk-import",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "items": [
                {"input_payload": {"q": "正常问题"}},
                {"input_payload": {"q": "联系 alice@example.com"}},
            ],
            "pii_strategy": "drop",
        },
    )
    data = r.json()["data"]
    assert data["added"] == 1
    assert data["dropped_pii"] == 1


async def test_bulk_import_rejects_empty(
    client: AsyncClient, admin_token: str
):
    cr = await client.post(
        "/v1/admin/datasets",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "bulk-empty-ds"},
    )
    did = cr.json()["data"]["id"]
    r = await client.post(
        f"/v1/admin/datasets/{did}/items/bulk-import",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"items": []},
    )
    assert r.status_code in (400, 422)


async def test_sample_is_idempotent(
    client: AsyncClient, admin_token: str, app_with_logs: dict
):
    cr = await client.post(
        "/v1/admin/datasets",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "idem"},
    )
    did = cr.json()["data"]["id"]

    # 跑两次采样：第二次全部 skip
    r1 = await client.post(
        f"/v1/admin/datasets/{did}/sample-from-logs",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"app_id": app_with_logs["app_key"], "limit": 10},
    )
    r2 = await client.post(
        f"/v1/admin/datasets/{did}/sample-from-logs",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"app_id": app_with_logs["app_key"], "limit": 10},
    )
    assert r1.json()["data"]["added"] == app_with_logs["log_count"]
    assert r2.json()["data"]["added"] == 0
    assert r2.json()["data"]["skipped"] == app_with_logs["log_count"]


async def test_sample_include_response_as_expected(
    client: AsyncClient, admin_token: str, app_with_logs: dict
):
    cr = await client.post(
        "/v1/admin/datasets",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "with-expected"},
    )
    did = cr.json()["data"]["id"]
    await client.post(
        f"/v1/admin/datasets/{did}/sample-from-logs",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "app_id": app_with_logs["app_key"],
            "limit": 10,
            "include_response_as_expected": True,
        },
    )
    items = (
        await client.get(
            f"/v1/admin/datasets/{did}/items",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    ).json()["data"]
    # 每条 expected_output 是 dict（含 answer）
    for it in items:
        assert it["expected_output"] is not None
        assert "answer" in it["expected_output"]


# ── 人工标注 ──────────────────────────────────────────────


async def test_update_item_expected(
    client: AsyncClient, admin_token: str, app_with_logs: dict
):
    cr = await client.post(
        "/v1/admin/datasets",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "annot"},
    )
    did = cr.json()["data"]["id"]
    await client.post(
        f"/v1/admin/datasets/{did}/sample-from-logs",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"app_id": app_with_logs["app_key"], "limit": 2},
    )
    items = (
        await client.get(
            f"/v1/admin/datasets/{did}/items",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    ).json()["data"]
    item_id = items[0]["id"]

    ur = await client.post(
        f"/v1/admin/datasets/items/{item_id}/update",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "expected_output": {"answer": "校准后的金标准"},
            "meta": {"reviewer": "links", "difficulty": "easy"},
        },
    )
    item = ur.json()["data"]
    assert item["expected_output"]["answer"] == "校准后的金标准"
    assert item["meta"]["reviewer"] == "links"
