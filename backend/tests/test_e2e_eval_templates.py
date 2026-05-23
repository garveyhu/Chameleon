"""P21.2 PR #62 E2E: EvalTemplate CRUD + 版本递增 + freeze 语义"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import EvalTemplate, Role, User, UserRole
from chameleon.core.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-et-{rand}"
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
async def _clean_templates():
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(delete(EvalTemplate))
        await s.commit()


def _hdr(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


# ── CRUD ───────────────────────────────────────────────


async def test_create_template_basic(client: AsyncClient, admin_token: str):
    r = await client.post(
        "/v1/admin/eval-templates",
        headers=_hdr(admin_token),
        json={
            "name": "RAG-4维",
            "description": "RAGAS 4 metric",
            "metrics": [
                {"name": "faith", "algorithm": "ragas_faithfulness", "weight": 0.3},
                {"name": "rel", "algorithm": "ragas_answer_relevance", "weight": 0.3},
                {"name": "prec", "algorithm": "ragas_context_precision", "weight": 0.2},
                {"name": "recall", "algorithm": "ragas_context_recall", "weight": 0.2},
            ],
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == "RAG-4维"
    assert data["version"] == 1
    assert len(data["metrics"]) == 4


async def test_create_duplicate_name_rejected(
    client: AsyncClient, admin_token: str
):
    payload = {
        "name": "dup",
        "metrics": [{"name": "m1", "algorithm": "ragas_faithfulness", "weight": 1.0}],
    }
    r1 = await client.post(
        "/v1/admin/eval-templates", headers=_hdr(admin_token), json=payload
    )
    assert r1.status_code == 200
    r2 = await client.post(
        "/v1/admin/eval-templates", headers=_hdr(admin_token), json=payload
    )
    # 同 name 重建 → 拒绝（要 update 走 version+=1）
    assert r2.status_code in (400, 500)


async def test_update_creates_new_version(
    client: AsyncClient, admin_token: str
):
    """update 不原地改；新建 version+=1 的行；老行保留"""
    cr = await client.post(
        "/v1/admin/eval-templates",
        headers=_hdr(admin_token),
        json={
            "name": "v-test",
            "metrics": [{"name": "m1", "algorithm": "ragas_faithfulness", "weight": 1.0}],
        },
    )
    v1_id = cr.json()["data"]["id"]

    ur = await client.post(
        f"/v1/admin/eval-templates/{v1_id}/update",
        headers=_hdr(admin_token),
        json={
            "metrics": [
                {"name": "m1", "algorithm": "ragas_faithfulness", "weight": 0.5},
                {"name": "m2", "algorithm": "ragas_answer_relevance", "weight": 0.5},
            ]
        },
    )
    assert ur.status_code == 200, ur.text
    data = ur.json()["data"]
    assert data["version"] == 2
    assert data["id"] != v1_id  # 新行
    assert len(data["metrics"]) == 2

    # 老 v1 还在（freeze 引用源）
    async with AsyncSessionLocal() as s:
        old = (
            await s.execute(
                select(EvalTemplate).where(EvalTemplate.id == v1_id)
            )
        ).scalar_one()
        assert old.version == 1
        assert len(old.metrics) == 1


async def test_list_returns_only_latest_per_name(
    client: AsyncClient, admin_token: str
):
    """list 只返每 name 最新 version；老 version 仍 DB 可读，但列表不展示"""
    cr = await client.post(
        "/v1/admin/eval-templates",
        headers=_hdr(admin_token),
        json={
            "name": "filt-test",
            "metrics": [{"name": "m1", "algorithm": "ragas_faithfulness", "weight": 1.0}],
        },
    )
    v1_id = cr.json()["data"]["id"]
    await client.post(
        f"/v1/admin/eval-templates/{v1_id}/update",
        headers=_hdr(admin_token),
        json={
            "metrics": [{"name": "m1", "algorithm": "ragas_answer_relevance", "weight": 1.0}],
        },
    )
    lr = await client.get(
        "/v1/admin/eval-templates", headers=_hdr(admin_token)
    )
    items = [i for i in lr.json()["data"] if i["name"] == "filt-test"]
    assert len(items) == 1
    assert items[0]["version"] == 2


async def test_delete_specific_version_only(
    client: AsyncClient, admin_token: str
):
    cr = await client.post(
        "/v1/admin/eval-templates",
        headers=_hdr(admin_token),
        json={
            "name": "del-test",
            "metrics": [{"name": "m1", "algorithm": "ragas_faithfulness", "weight": 1.0}],
        },
    )
    v1_id = cr.json()["data"]["id"]
    ur = await client.post(
        f"/v1/admin/eval-templates/{v1_id}/update",
        headers=_hdr(admin_token),
        json={"description": "v2"},
    )
    v2_id = ur.json()["data"]["id"]

    dr = await client.post(
        f"/v1/admin/eval-templates/{v2_id}/delete",
        headers=_hdr(admin_token),
    )
    assert dr.status_code == 200

    # v1 还在
    async with AsyncSessionLocal() as s:
        v1 = (
            await s.execute(
                select(EvalTemplate).where(EvalTemplate.id == v1_id)
            )
        ).scalar_one_or_none()
        assert v1 is not None


async def test_validate_metrics_required(
    client: AsyncClient, admin_token: str
):
    r = await client.post(
        "/v1/admin/eval-templates",
        headers=_hdr(admin_token),
        json={"name": "no-metrics", "metrics": []},
    )
    assert r.status_code in (400, 422)


async def test_validate_weights_sum(
    client: AsyncClient, admin_token: str
):
    r = await client.post(
        "/v1/admin/eval-templates",
        headers=_hdr(admin_token),
        json={
            "name": "zero-w",
            "metrics": [
                {"name": "m1", "algorithm": "ragas_faithfulness", "weight": 0.0}
            ],
        },
    )
    assert r.status_code in (400, 422)
