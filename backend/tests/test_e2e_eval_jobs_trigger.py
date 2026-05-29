"""P19.1 PR #30 E2E：手动触发 eval_job 写 eval_job_run + delta_score 计算

策略：用 monkeypatch 替换 datasets.runner.run_dataset 返回假 DatasetRun，
避免依赖真实 LLM。验证：
- eval_job_run 行写入正确
- mean_score 取自 dataset_run.summary
- 第二次触发的 delta_score = new - prev
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import (
    Dataset,
    DatasetRun,
    EvalJob,
    EvalJobRun,
    Role,
    User,
    UserRole,
)
from chameleon.data.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-ejt-{rand}"
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
async def job_id(admin_token: str, client: AsyncClient):
    async with AsyncSessionLocal() as s:
        ds = Dataset(name=f"trigger-ds-{secrets.token_hex(2)}", item_count=1)
        s.add(ds)
        await s.commit()
        await s.refresh(ds)
        did = ds.id

    r = await client.post(
        "/v1/admin/eval-jobs",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "job_key": f"trigger-job-{secrets.token_hex(2)}",
            "name": "trigger test",
            "dataset_id": did,
            "cron_expr": "0 0 * * *",
            "judge": "exact_match",
        },
    )
    assert r.status_code == 200
    jid = r.json()["data"]["id"]
    yield jid

    async with AsyncSessionLocal() as s:
        await s.execute(delete(EvalJobRun).where(EvalJobRun.job_id == jid))
        await s.execute(delete(EvalJob).where(EvalJob.id == jid))
        await s.execute(delete(DatasetRun).where(DatasetRun.dataset_id == did))
        await s.execute(delete(Dataset).where(Dataset.id == did))
        await s.commit()


def _make_fake_runner(mean_score: float):
    """构造一个 run_dataset 替身：写入真 DatasetRun + summary，绕过 LLM 调用"""

    async def fake_run_dataset(session, **kwargs):
        run = DatasetRun(
            dataset_id=kwargs["dataset_id"],
            name=kwargs.get("name", "fake"),
            judge=kwargs.get("judge", "exact_match"),
            status="success",
            summary={
                "total": 1,
                "ok": 1,
                "fail": 0,
                "mean_score": mean_score,
                "score_count": 1,
            },
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run

    return fake_run_dataset


async def test_trigger_writes_job_run_and_mean_score(
    client: AsyncClient,
    admin_token: str,
    job_id: int,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "chameleon.system.eval_jobs.service.ds_runner.run_dataset",
        _make_fake_runner(0.85),
    )

    r = await client.post(
        f"/v1/admin/eval-jobs/{job_id}/trigger",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "success"
    assert Decimal(data["mean_score"]) == Decimal("0.8500")

    # eval_job_run + job.last_score 写入了
    async with AsyncSessionLocal() as s:
        run = (
            await s.execute(
                select(EvalJobRun).where(EvalJobRun.job_id == job_id)
            )
        ).scalar_one()
        assert run.triggered_by == "manual"
        assert run.status == "success"
        assert run.mean_score == Decimal("0.8500")
        assert run.delta_score is None  # 第一次没有前值

        job = (
            await s.execute(select(EvalJob).where(EvalJob.id == job_id))
        ).scalar_one()
        assert job.last_score == Decimal("0.8500")
        assert job.last_run_at is not None


async def test_trigger_computes_delta_score(
    client: AsyncClient,
    admin_token: str,
    job_id: int,
    monkeypatch: pytest.MonkeyPatch,
):
    # 第一次
    monkeypatch.setattr(
        "chameleon.system.eval_jobs.service.ds_runner.run_dataset",
        _make_fake_runner(0.80),
    )
    r1 = await client.post(
        f"/v1/admin/eval-jobs/{job_id}/trigger",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r1.status_code == 200

    # 第二次：分数下跌 0.30
    monkeypatch.setattr(
        "chameleon.system.eval_jobs.service.ds_runner.run_dataset",
        _make_fake_runner(0.50),
    )
    r2 = await client.post(
        f"/v1/admin/eval-jobs/{job_id}/trigger",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r2.status_code == 200

    # 列 runs：应该有 2 行；新的 delta_score = 0.50 - 0.80 = -0.30
    runs_r = await client.get(
        f"/v1/admin/eval-jobs/{job_id}/runs",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    runs = runs_r.json()["data"]
    assert len(runs) == 2
    # 按 created_at desc 排，最新的在前
    latest = runs[0]
    prev = runs[1]
    assert Decimal(latest["mean_score"]) == Decimal("0.5000")
    assert Decimal(latest["delta_score"]) == Decimal("-0.3000")
    assert prev["delta_score"] is None


async def test_trigger_disabled_job_rejected(
    client: AsyncClient,
    admin_token: str,
    job_id: int,
):
    # 禁用该 job
    await client.post(
        f"/v1/admin/eval-jobs/{job_id}/update",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"enabled": False},
    )
    r = await client.post(
        f"/v1/admin/eval-jobs/{job_id}/trigger",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code in (400, 500)
    assert r.json()["success"] is False
