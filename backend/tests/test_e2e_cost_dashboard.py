"""P22.1 PR #72 E2E: cost dashboard 3 个 endpoint"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import (
    CallLog,
    ModelPricing,
    Role,
    User,
    UserRole,
)
from chameleon.data.utils.passwords import hash_password
from chameleon.data.utils.snowflake import next_id
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-cost-{rand}"
    password = "TestPwd123!"
    async with AsyncSessionLocal() as s:
        rid = (
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
        s.add(UserRole(user_id=u.id, role_id=rid))
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


@pytest_asyncio.fixture
async def seeded_calls_with_cost():
    """造 1 app + 几条带 cost_usd 的 call_log"""
    suffix = secrets.token_hex(3)
    app_key = f"e2e-cost-app-{suffix}"
    async with AsyncSessionLocal() as s:
        now = datetime.now(timezone.utc)
        for i, (agent, cost) in enumerate(
            [
                ("alpha", 0.005),
                ("alpha", 0.003),
                ("beta", 0.010),
                ("alpha", 0.002),
                ("gamma", 0.020),
            ]
        ):
            s.add(
                CallLog(
                    id=next_id(),
                    request_id=f"rid-cost-{suffix}-{i}",
                    app_id=app_key,
                    agent_key=agent,
                    session_id=None,
                    stream=False,
                    success=True,
                    code=200,
                    duration_ms=100,
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150,
                    cost_usd=cost,
                    parent_id=None,
                    observation_type="trace",
                    created_at=now - timedelta(hours=i),
                )
            )
        await s.commit()
    yield {"app_key": app_key, "suffix": suffix}
    async with AsyncSessionLocal() as s:
        await s.execute(delete(CallLog).where(CallLog.app_id == app_key))
        await s.commit()


@pytest_asyncio.fixture
async def seeded_multidim_calls():
    """造 user，几条带 user/model 的 call_log，验证多维度聚合（app_id 为来源标签）"""
    suffix = secrets.token_hex(3)
    app_key = f"md-app-{suffix}"
    model_code = f"md-model-{suffix}"
    async with AsyncSessionLocal() as s:
        u = User(
            username=f"md-user-{suffix}",
            password_hash=hash_password("Pwd123!xx"),
            status="active",
            must_change_password=False,
        )
        s.add(u)
        await s.flush()
        uid = u.id
        now = datetime.now(timezone.utc)
        # 3 条：cost 0.01 / 0.02 / 0.03
        for i, cost in enumerate([0.01, 0.02, 0.03]):
            s.add(
                CallLog(
                    id=next_id(),
                    request_id=f"rid-md-{suffix}-{i}",
                    app_id=app_key,
                    agent_key="md-agent",
                    user_id=uid,
                    model_code=model_code,
                    success=True,
                    code=200,
                    duration_ms=100,
                    cost_usd=cost,
                    parent_id=None,
                    observation_type="trace",
                    created_at=now - timedelta(minutes=i),
                )
            )
        await s.commit()
    yield {
        "app_key": app_key,
        "user_id": uid,
        "model_code": model_code,
    }
    async with AsyncSessionLocal() as s:
        await s.execute(delete(CallLog).where(CallLog.app_id == app_key))
        await s.execute(delete(User).where(User.id == uid))
        await s.commit()


def _hdr(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


async def _by_dim(
    client: AsyncClient, token: str, dimension: str, *, limit: int = 50
) -> list[dict]:
    # limit=50：top-N 是全局聚合，并行/同套件其它用例也会造共享维度的
    # 数据，用最大 limit 降低被挤出 top-N 的偶发失败
    r = await client.get(
        f"/v1/admin/dashboard/cost/by-dimension?dimension={dimension}"
        f"&hours=24&limit={limit}",
        headers=_hdr(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ── /cost/totals ─────────────────────────────────────


async def test_cost_totals_sums_in_range(
    client: AsyncClient, admin_token: str, seeded_calls_with_cost: dict
):
    r = await client.get(
        "/v1/admin/dashboard/cost/totals?hours=24",
        headers=_hdr(admin_token),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    # 5 条 calls 总额 = 0.005+0.003+0.010+0.002+0.020 = 0.040
    assert data["total_usd"] >= 0.039
    assert data["total_calls"] >= 5


async def test_cost_totals_with_explicit_range(
    client: AsyncClient, admin_token: str, seeded_calls_with_cost: dict
):
    now = datetime.now(timezone.utc)
    r = await client.get(
        "/v1/admin/dashboard/cost/totals",
        params={
            "from_ts": (now - timedelta(hours=24)).isoformat(),
            "to_ts": now.isoformat(),
        },
        headers=_hdr(admin_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["total_calls"] >= 5


# ── /cost/by-dimension ───────────────────────────────


async def test_cost_by_agent_returns_topn(
    client: AsyncClient, admin_token: str, seeded_calls_with_cost: dict
):
    r = await client.get(
        "/v1/admin/dashboard/cost/by-dimension?dimension=agent_key&hours=24&limit=5",
        headers=_hdr(admin_token),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    labels = [row["label"] for row in data]
    # alpha 出现 3 次合计 0.010；gamma 1 次 0.020；按 cost 降序 gamma 应该在前
    assert "gamma" in labels
    assert "alpha" in labels


async def test_cost_by_app_returns_correct_total(
    client: AsyncClient, admin_token: str, seeded_calls_with_cost: dict
):
    r = await client.get(
        "/v1/admin/dashboard/cost/by-dimension?dimension=app_id&hours=24",
        headers=_hdr(admin_token),
    )
    assert r.status_code == 200
    data = r.json()["data"]
    target = [
        row for row in data if row["label"] == seeded_calls_with_cost["app_key"]
    ]
    assert len(target) == 1
    assert target[0]["calls"] >= 5
    assert target[0]["cost_usd"] >= 0.039


async def test_cost_by_invalid_dimension_rejected(
    client: AsyncClient, admin_token: str
):
    r = await client.get(
        "/v1/admin/dashboard/cost/by-dimension?dimension=not-a-field",
        headers=_hdr(admin_token),
    )
    assert r.status_code in (400, 422)


# ── 多维聚合（user / model） ──────────────────────────


async def test_cost_by_user_dimension(
    client: AsyncClient, admin_token: str, seeded_multidim_calls: dict
):
    data = await _by_dim(client, admin_token, "user_id")
    row = next(
        r for r in data if r["label"] == str(seeded_multidim_calls["user_id"])
    )
    assert abs(row["cost_usd"] - 0.06) < 1e-6  # 0.01+0.02+0.03
    # effective_cost = 原始 cost（不再乘倍率）
    assert abs(row["effective_cost_usd"] - 0.06) < 1e-6
    assert row["calls"] == 3


async def test_cost_by_model_dimension(
    client: AsyncClient, admin_token: str, seeded_multidim_calls: dict
):
    data = await _by_dim(client, admin_token, "model_code")
    labels = [r["label"] for r in data]
    assert seeded_multidim_calls["model_code"] in labels


# ── /cost/timeseries ─────────────────────────────────


async def test_cost_timeseries_hour_bucket(
    client: AsyncClient, admin_token: str, seeded_calls_with_cost: dict
):
    r = await client.get(
        "/v1/admin/dashboard/cost/timeseries?hours=24&bucket=hour",
        headers=_hdr(admin_token),
    )
    assert r.status_code == 200
    points = r.json()["data"]
    assert isinstance(points, list)
    # 5 条不同 hour 的 calls → 至少 1 个点
    assert len(points) >= 1
    total = sum(p["cost_usd"] for p in points)
    assert total >= 0.039


async def test_cost_timeseries_day_bucket(
    client: AsyncClient, admin_token: str, seeded_calls_with_cost: dict
):
    r = await client.get(
        "/v1/admin/dashboard/cost/timeseries?hours=48&bucket=day",
        headers=_hdr(admin_token),
    )
    assert r.status_code == 200


async def test_cost_timeseries_invalid_bucket(
    client: AsyncClient, admin_token: str
):
    r = await client.get(
        "/v1/admin/dashboard/cost/timeseries?bucket=week",
        headers=_hdr(admin_token),
    )
    assert r.status_code in (400, 422)


# 确保未使用 import 不报 lint
_ = ModelPricing
