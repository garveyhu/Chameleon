"""P21.2 PR #64 E2E：EvalTemplate 联动 + 评分分布"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import (
    Dataset,
    DatasetItem,
    DatasetRun,
    DatasetRunItem,
    EvalTemplate,
    Role,
    User,
    UserRole,
)
from chameleon.core.utils.passwords import hash_password
from chameleon.system.datasets.template_scoring import (
    score_run_with_template,
)
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-es-{rand}"
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


@pytest_asyncio.fixture
async def seeded_run_and_template():
    """造 1 dataset + 3 items + 1 dataset_run + 3 run_items + 1 template"""
    async with AsyncSessionLocal() as s:
        ds = Dataset(name=f"es-{secrets.token_hex(3)}", item_count=3)
        s.add(ds)
        await s.flush()
        items = []
        for i, q in enumerate(["问题一", "问题二", "问题三"]):
            it = DatasetItem(
                dataset_id=ds.id,
                input_payload={"q": q},
                expected_output={"answer": f"答案-{i}"},
            )
            s.add(it)
            items.append(it)
        run = DatasetRun(
            dataset_id=ds.id, name="rn", status="success", judge="exact_match"
        )
        s.add(run)
        await s.flush()
        run_items = []
        for i, it in enumerate(items):
            ri = DatasetRunItem(
                dataset_run_id=run.id,
                dataset_item_id=it.id,
                actual_output={
                    "answer": f"模型回答-{i}",
                    "citations": [{"content": "context-1"}, {"content": "context-2"}],
                },
                score=None,
                error=None,
                duration_ms=100,
            )
            s.add(ri)
            run_items.append(ri)
        tmpl = EvalTemplate(
            name=f"tmpl-{secrets.token_hex(3)}",
            metrics=[
                {"name": "faith", "algorithm": "ragas_faithfulness", "weight": 0.5},
                {"name": "prec", "algorithm": "ragas_context_precision", "weight": 0.5},
            ],
            version=1,
        )
        s.add(tmpl)
        await s.commit()
        await s.refresh(ds)
        await s.refresh(run)
        await s.refresh(tmpl)
        yield {
            "dataset_id": ds.id,
            "run_id": run.id,
            "template_id": tmpl.id,
            "item_ids": [it.id for it in items],
        }

    async with AsyncSessionLocal() as s:
        await s.execute(delete(DatasetRunItem).where(DatasetRunItem.dataset_run_id == run.id))
        await s.execute(delete(DatasetRun).where(DatasetRun.id == run.id))
        await s.execute(delete(DatasetItem).where(DatasetItem.dataset_id == ds.id))
        await s.execute(delete(Dataset).where(Dataset.id == ds.id))
        await s.execute(delete(EvalTemplate).where(EvalTemplate.id == tmpl.id))
        await s.commit()


def _hdr(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


# ── score_run_with_template ───────────────────────────────


async def test_score_run_with_template_writes_eval_scores(
    seeded_run_and_template: dict,
):
    async with AsyncSessionLocal() as s:
        tmpl = (
            await s.execute(
                select(EvalTemplate).where(
                    EvalTemplate.id == seeded_run_and_template["template_id"]
                )
            )
        ).scalar_one()
        summary = await score_run_with_template(
            s, run_id=seeded_run_and_template["run_id"], template=tmpl
        )
        await s.commit()
        assert summary["scored_items"] == 3
        assert summary["weighted_total_mean"] is not None

        rows = (
            (
                await s.execute(
                    select(DatasetRunItem).where(
                        DatasetRunItem.dataset_run_id
                        == seeded_run_and_template["run_id"]
                    )
                )
            )
            .scalars()
            .all()
        )
        for r in rows:
            assert r.eval_scores is not None
            assert "weighted_total" in r.eval_scores
            assert "faith" in r.eval_scores or "prec" in r.eval_scores


async def test_score_run_no_metrics_template():
    """空 metrics template → summary 不挂 weighted_total"""
    async with AsyncSessionLocal() as s:
        empty_tmpl = EvalTemplate(
            name=f"empty-{secrets.token_hex(3)}", metrics=[], version=1
        )
        s.add(empty_tmpl)
        ds = Dataset(name=f"empty-{secrets.token_hex(3)}", item_count=0)
        s.add(ds)
        await s.flush()
        run = DatasetRun(
            dataset_id=ds.id, name="r", status="success", judge="exact_match"
        )
        s.add(run)
        await s.commit()
        try:
            summary = await score_run_with_template(
                s, run_id=run.id, template=empty_tmpl
            )
            assert summary["scored_items"] == 0
        finally:
            await s.execute(delete(DatasetRun).where(DatasetRun.id == run.id))
            await s.execute(delete(Dataset).where(Dataset.id == ds.id))
            await s.execute(
                delete(EvalTemplate).where(EvalTemplate.id == empty_tmpl.id)
            )
            await s.commit()


# ── distribution endpoint ────────────────────────────────


async def test_score_distribution_endpoint_returns_buckets(
    client: AsyncClient,
    admin_token: str,
    seeded_run_and_template: dict,
):
    # 先跑 template 评分填充 eval_scores
    async with AsyncSessionLocal() as s:
        tmpl = (
            await s.execute(
                select(EvalTemplate).where(
                    EvalTemplate.id == seeded_run_and_template["template_id"]
                )
            )
        ).scalar_one()
        await score_run_with_template(
            s, run_id=seeded_run_and_template["run_id"], template=tmpl
        )
        await s.commit()

    r = await client.get(
        f"/v1/admin/datasets/runs/{seeded_run_and_template['run_id']}/score-distribution",
        headers=_hdr(admin_token),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert str(data["run_id"]) == str(seeded_run_and_template["run_id"])
    assert data["total_scored_items"] >= 1
    assert isinstance(data["metrics"], list)
    assert len(data["metrics"]) >= 1
    first = data["metrics"][0]
    assert "buckets" in first
    assert len(first["buckets"]) == 10  # default
    total_in_buckets = sum(b["count"] for b in first["buckets"])
    assert total_in_buckets >= 1


async def test_score_distribution_low_threshold_marks_items(
    client: AsyncClient,
    admin_token: str,
    seeded_run_and_template: dict,
):
    """threshold=1.0 时所有 < 1.0 的 item 都会被列在 low_score_item_ids"""
    async with AsyncSessionLocal() as s:
        tmpl = (
            await s.execute(
                select(EvalTemplate).where(
                    EvalTemplate.id == seeded_run_and_template["template_id"]
                )
            )
        ).scalar_one()
        await score_run_with_template(
            s, run_id=seeded_run_and_template["run_id"], template=tmpl
        )
        await s.commit()

    r = await client.get(
        f"/v1/admin/datasets/runs/{seeded_run_and_template['run_id']}/score-distribution?threshold=1.0",
        headers=_hdr(admin_token),
    )
    assert r.status_code == 200
    metrics = r.json()["data"]["metrics"]
    # default_judge_fn 全 yes → score=1.0 没人 low；这条主要测 endpoint 接受 threshold 参数
    assert all(isinstance(m["low_score_item_ids"], list) for m in metrics)


async def test_score_distribution_buckets_parameter(
    client: AsyncClient,
    admin_token: str,
    seeded_run_and_template: dict,
):
    async with AsyncSessionLocal() as s:
        tmpl = (
            await s.execute(
                select(EvalTemplate).where(
                    EvalTemplate.id == seeded_run_and_template["template_id"]
                )
            )
        ).scalar_one()
        await score_run_with_template(
            s, run_id=seeded_run_and_template["run_id"], template=tmpl
        )
        await s.commit()

    r = await client.get(
        f"/v1/admin/datasets/runs/{seeded_run_and_template['run_id']}/score-distribution?buckets=5",
        headers=_hdr(admin_token),
    )
    metrics = r.json()["data"]["metrics"]
    if metrics:
        assert len(metrics[0]["buckets"]) == 5
