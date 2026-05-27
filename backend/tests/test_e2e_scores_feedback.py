"""P17.C2 scores 表 + Feedback API E2E

覆盖：
- 鉴权 401
- admin 创建 score（数值 + 文本两种 data_type）
- 列表按 call_log_id / trace_id 过滤
- 创建脏 call_log_id 不存在 → 失败
- value/string_value 一致性校验
- widget feedback：embed_key + origin 白名单 + 落 scores 行
- feedback trace_id 不存在 → 失败
"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import (
    Agent,
    CallLog,
    EmbedConfig,
    Role,
    Score,
    User,
    UserRole,
)
from chameleon.core.utils.passwords import hash_password
from chameleon.system.api_key.service import record_call
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-sc-{rand}"
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
async def trace_with_log():
    """临时 app + 一条 call_log（作为 score 的载体）"""
    suffix = secrets.token_hex(3)
    app_key = f"sc-app-{suffix}"
    rid = f"sc-rid-{suffix}"
    async with AsyncSessionLocal() as s:
        await record_call(
            s,
            request_id=rid,
            app_id=app_key,
            agent_key="example",
            session_id=None,
            stream=False,
            success=True,
            code=200,
            error_message=None,
            duration_ms=120,
            observation_type="trace",
        )
        await s.commit()
    yield {"app_key": app_key, "request_id": rid}

    async with AsyncSessionLocal() as s:
        await s.execute(delete(Score).where(Score.call_log_id == rid))
        await s.execute(delete(CallLog).where(CallLog.app_id == app_key))
        await s.commit()


# ── admin scores API ──────────────────────────────────────


async def test_scores_requires_auth(client: AsyncClient):
    r = await client.get("/v1/admin/scores")
    assert r.status_code == 401


async def test_create_score_numeric(
    client: AsyncClient, admin_token: str, trace_with_log: dict
):
    r = await client.post(
        "/v1/admin/scores",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "call_log_id": trace_with_log["request_id"],
            "trace_id": trace_with_log["request_id"],
            "name": "ragas_faithfulness",
            "value": 0.83,
            "data_type": "numeric",
            "source": "eval",
        },
    )
    assert r.status_code == 200, r.text
    item = r.json()["data"]
    assert item["name"] == "ragas_faithfulness"
    assert item["value"] == 0.83
    assert item["data_type"] == "numeric"
    assert item["source"] == "eval"


async def test_create_score_categorical(
    client: AsyncClient, admin_token: str, trace_with_log: dict
):
    r = await client.post(
        "/v1/admin/scores",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "call_log_id": trace_with_log["request_id"],
            "name": "sentiment",
            "string_value": "positive",
            "data_type": "categorical",
            "source": "annotation",
            "comment": "看起来回答得不错",
        },
    )
    assert r.status_code == 200
    item = r.json()["data"]
    assert item["string_value"] == "positive"
    assert item["data_type"] == "categorical"
    assert item["comment"] == "看起来回答得不错"


async def test_create_score_bad_call_log(
    client: AsyncClient, admin_token: str
):
    r = await client.post(
        "/v1/admin/scores",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "call_log_id": "not-exist",
            "name": "x",
            "value": 1,
            "data_type": "numeric",
        },
    )
    body = r.json()
    assert body["success"] is False
    assert "不存在" in body["message"]


async def test_create_score_inconsistent_data_type(
    client: AsyncClient, admin_token: str, trace_with_log: dict
):
    """numeric data_type 但没传 value → 422"""
    r = await client.post(
        "/v1/admin/scores",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "call_log_id": trace_with_log["request_id"],
            "name": "x",
            "data_type": "numeric",
        },
    )
    body = r.json()
    assert body["success"] is False
    assert "value" in body["message"]


async def test_list_scores_by_call_log(
    client: AsyncClient, admin_token: str, trace_with_log: dict
):
    # 先写两条
    for name in ("thumbs_up", "rating"):
        await client.post(
            "/v1/admin/scores",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "call_log_id": trace_with_log["request_id"],
                "name": name,
                "value": 1.0,
                "data_type": "numeric",
            },
        )
    r = await client.get(
        f"/v1/admin/scores?call_log_id={trace_with_log['request_id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    items = r.json()["data"]
    names = {it["name"] for it in items}
    assert {"thumbs_up", "rating"}.issubset(names)


# ── widget feedback ───────────────────────────────────────


@pytest_asyncio.fixture
async def embed_target(trace_with_log: dict):
    """临时 agent + embed_config，与 trace_with_log 共用 trace_id"""
    suffix = secrets.token_hex(3)
    embed_key = f"sc-emb-{suffix}"
    async with AsyncSessionLocal() as s:
        # 任意一个 agent
        ag = (await s.execute(select(Agent).limit(1))).scalar_one_or_none()
        assert ag is not None, "需要至少一个 agent 才能跑 embed feedback 测"
        cfg = EmbedConfig(
            embed_key=embed_key,
            agent_id=ag.id,
            name="sc embed",
            enabled=True,
            allowed_origins=["https://example.com"],
        )
        s.add(cfg)
        await s.flush()
        cid = cfg.id
        await s.commit()
    yield {**trace_with_log, "embed_key": embed_key}

    async with AsyncSessionLocal() as s:
        await s.execute(delete(EmbedConfig).where(EmbedConfig.id == cid))
        await s.commit()


async def test_feedback_records_score(
    client: AsyncClient, embed_target: dict
):
    r = await client.post(
        f"/v1/embed/{embed_target['embed_key']}/feedback",
        headers={"Origin": "https://example.com"},
        json={
            "trace_id": embed_target["request_id"],
            "name": "thumbs",
            "value": 1,
            "comment": "好",
        },
    )
    assert r.status_code == 200, r.text
    item = r.json()["data"]
    assert item["source"] == "feedback"
    assert item["data_type"] == "numeric"
    assert item["value"] == 1.0

    # DB 里能查到
    async with AsyncSessionLocal() as s:
        rows = (
            await s.execute(
                select(Score).where(
                    Score.call_log_id == embed_target["request_id"]
                )
            )
        ).scalars().all()
        assert any(r.source == "feedback" for r in rows)


async def test_feedback_unknown_trace(
    client: AsyncClient, embed_target: dict
):
    r = await client.post(
        f"/v1/embed/{embed_target['embed_key']}/feedback",
        headers={"Origin": "https://example.com"},
        json={"trace_id": "ghost-trace", "name": "x", "value": 1},
    )
    body = r.json()
    assert body["success"] is False
    assert "不存在" in body["message"]


async def test_feedback_origin_blocked(
    client: AsyncClient, embed_target: dict
):
    r = await client.post(
        f"/v1/embed/{embed_target['embed_key']}/feedback",
        headers={"Origin": "https://evil.com"},
        json={
            "trace_id": embed_target["request_id"],
            "name": "x",
            "value": 1,
        },
    )
    body = r.json()
    assert body["success"] is False
