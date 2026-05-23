"""P19.1 PR #30 E2E：eval_jobs CRUD + cron/judge 校验"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import (
    Dataset,
    EvalJob,
    EvalJobRun,
    Role,
    User,
    UserRole,
)
from chameleon.core.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-ej-{rand}"
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
async def dataset_id():
    """一次性建一个空 dataset 给所有 CRUD 测试用"""
    async with AsyncSessionLocal() as s:
        ds = Dataset(name=f"ej-test-{secrets.token_hex(2)}", item_count=0)
        s.add(ds)
        await s.commit()
        await s.refresh(ds)
        did = ds.id
    yield did
    async with AsyncSessionLocal() as s:
        await s.execute(delete(Dataset).where(Dataset.id == did))
        await s.commit()


@pytest_asyncio.fixture(autouse=True)
async def _clean_jobs():
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(delete(EvalJobRun))
        await s.execute(delete(EvalJob))
        await s.commit()


# ── 鉴权 ─────────────────────────────────────────────────


async def test_eval_jobs_requires_auth(client: AsyncClient):
    r = await client.get("/v1/admin/eval-jobs")
    assert r.status_code == 401


# ── CRUD ─────────────────────────────────────────────────


async def test_create_and_list_eval_job(
    client: AsyncClient, admin_token: str, dataset_id: int
):
    payload = {
        "job_key": "daily-baseline",
        "name": "Daily baseline",
        "dataset_id": dataset_id,
        "cron_expr": "0 2 * * *",
        "judge": "exact_match",
    }
    r = await client.post(
        "/v1/admin/eval-jobs",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=payload,
    )
    assert r.status_code == 200, r.text
    item = r.json()["data"]
    assert item["job_key"] == "daily-baseline"
    assert item["cron_expr"] == "0 2 * * *"
    assert item["enabled"] is True

    list_r = await client.get(
        "/v1/admin/eval-jobs",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert item["id"] in [j["id"] for j in list_r.json()["data"]]


async def test_update_and_delete_eval_job(
    client: AsyncClient, admin_token: str, dataset_id: int
):
    cr = await client.post(
        "/v1/admin/eval-jobs",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "job_key": "weekly-job",
            "name": "x",
            "dataset_id": dataset_id,
            "cron_expr": "0 0 * * 0",
        },
    )
    jid = cr.json()["data"]["id"]

    ur = await client.post(
        f"/v1/admin/eval-jobs/{jid}/update",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "renamed", "enabled": False},
    )
    assert ur.json()["data"]["name"] == "renamed"
    assert ur.json()["data"]["enabled"] is False

    dr = await client.post(
        f"/v1/admin/eval-jobs/{jid}/delete",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert dr.status_code == 200


# ── 校验 ────────────────────────────────────────────────


async def test_create_rejects_bad_cron(
    client: AsyncClient, admin_token: str, dataset_id: int
):
    r = await client.post(
        "/v1/admin/eval-jobs",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "job_key": "bad-cron",
            "name": "x",
            "dataset_id": dataset_id,
            "cron_expr": "totally bogus",
        },
    )
    assert r.status_code in (400, 500)
    body = r.json()
    assert body["success"] is False


async def test_create_rejects_bad_judge(
    client: AsyncClient, admin_token: str, dataset_id: int
):
    r = await client.post(
        "/v1/admin/eval-jobs",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "job_key": "bad-judge",
            "name": "x",
            "dataset_id": dataset_id,
            "cron_expr": "0 0 * * *",
            "judge": "no_such_judge",
        },
    )
    assert r.status_code in (400, 500)
    assert r.json()["success"] is False


async def test_create_rejects_missing_dataset(
    client: AsyncClient, admin_token: str
):
    r = await client.post(
        "/v1/admin/eval-jobs",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "job_key": "no-ds",
            "name": "x",
            "dataset_id": 99999999,  # 不存在
            "cron_expr": "0 0 * * *",
        },
    )
    assert r.status_code in (400, 500)
    assert r.json()["success"] is False


async def test_duplicate_job_key_rejected(
    client: AsyncClient, admin_token: str, dataset_id: int
):
    payload = {
        "job_key": "dup-key",
        "name": "x",
        "dataset_id": dataset_id,
        "cron_expr": "0 0 * * *",
    }
    r1 = await client.post(
        "/v1/admin/eval-jobs",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=payload,
    )
    assert r1.status_code == 200
    r2 = await client.post(
        "/v1/admin/eval-jobs",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=payload,
    )
    assert r2.status_code in (400, 500)
    assert r2.json()["success"] is False
