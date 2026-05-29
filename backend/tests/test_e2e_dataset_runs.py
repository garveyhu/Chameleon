"""P18.3 PR #25 E2E：dataset_runs + judges + scores 串联 + 对比"""

from __future__ import annotations

import secrets
from typing import Any

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import (
    CallLog,
    Dataset,
    DatasetItem,
    DatasetRun,
    DatasetRunItem,
    Role,
    Score,
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
    username = f"e2e-dr-{rand}"
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
async def seeded_dataset(client: AsyncClient, admin_token: str):
    """建一个 dataset，从临时 app 采 3 条样本"""
    suffix = secrets.token_hex(3)
    app_key = f"e2e-drapp-{suffix}"

    async with AsyncSessionLocal() as s:
        for i in range(3):
            await record_call(
                s,
                request_id=f"rid-dr-{suffix}-{i}",
                app_id=app_key,
                agent_key="example",
                session_id=None,
                stream=False,
                success=True,
                code=200,
                error_message=None,
                duration_ms=120,
                request_payload={"user_input": f"Question #{i}"},
                response_payload={"answer": f"Answer #{i}"},
                observation_type="trace",
            )
        await s.commit()

    cr = await client.post(
        "/v1/admin/datasets",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": f"dr-ds-{suffix}"},
    )
    did = cr.json()["data"]["id"]
    await client.post(
        f"/v1/admin/datasets/{did}/sample-from-logs",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"app_id": app_key, "limit": 10},
    )
    yield {"dataset_id": did, "app_key": app_key, "suffix": suffix}

    async with AsyncSessionLocal() as s:
        await s.execute(delete(Score).where(Score.source == "eval"))
        await s.execute(delete(DatasetRunItem))
        await s.execute(delete(DatasetRun))
        await s.execute(delete(DatasetItem))
        await s.execute(delete(Dataset).where(Dataset.id == did))
        await s.execute(delete(CallLog).where(CallLog.app_id == app_key))
        await s.commit()


class _MockLLM:
    """ainvoke 永远返同一个回答"""

    def __init__(self, response: str):
        self.response = response
        self.model_name = "mock"

    async def ainvoke(self, messages, **kwargs) -> Any:
        class _AI:
            content = self.response
            usage_metadata = {"input_tokens": 1, "output_tokens": 1}

        return _AI()


# ── 跑 + judge ─────────────────────────────────────────────


async def test_list_judges(
    client: AsyncClient, admin_token: str
):
    r = await client.get(
        "/v1/admin/datasets/judges",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    judges = r.json()["data"]
    assert {"exact_match", "contains", "llm_judge"}.issubset(judges)


async def test_run_dataset_with_exact_match_all_fail(
    client: AsyncClient, admin_token: str, seeded_dataset: dict
):
    """mock LLM 返 'wrong'；expected="Answer #N" → 全 score=0"""
    from chameleon.core.components.llms import factory as llm_factory

    llm_factory.set_for_test(_MockLLM("wrong"))  # type: ignore[arg-type]
    try:
        r = await client.post(
            f"/v1/admin/datasets/{seeded_dataset['dataset_id']}/run",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "exact-fail", "judge": "exact_match"},
        )
        assert r.status_code == 200, r.text
        run = r.json()["data"]
        assert run["status"] == "success"
        assert run["summary"]["total"] == 3
        assert run["summary"]["mean_score"] == 0.0
    finally:
        llm_factory.set_for_test(None)


async def test_run_dataset_with_contains_some_pass(
    client: AsyncClient, admin_token: str, seeded_dataset: dict
):
    """mock LLM 返 'XXAnswer #0YY'；contains 期望 'Answer #N' → 仅 #0 命中"""
    from chameleon.core.components.llms import factory as llm_factory

    llm_factory.set_for_test(_MockLLM("XXAnswer #0YY"))  # type: ignore[arg-type]
    try:
        r = await client.post(
            f"/v1/admin/datasets/{seeded_dataset['dataset_id']}/run",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "contains-mix", "judge": "contains"},
        )
        run = r.json()["data"]
        assert run["status"] == "success"
        # 3 个 item 里只有第一个 expected 'Answer #0' 被命中
        mean = run["summary"]["mean_score"]
        # 估算：1/3 命中 → mean 约 0.33
        assert 0.0 < mean < 0.5
    finally:
        llm_factory.set_for_test(None)


async def test_run_writes_scores_table(
    client: AsyncClient, admin_token: str, seeded_dataset: dict
):
    """run 跑完应往 scores 表写 source='eval' 行"""
    from chameleon.core.components.llms import factory as llm_factory

    llm_factory.set_for_test(_MockLLM("Answer #0"))  # type: ignore[arg-type]
    try:
        rr = await client.post(
            f"/v1/admin/datasets/{seeded_dataset['dataset_id']}/run",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "score-write", "judge": "contains"},
        )
        run_id = rr.json()["data"]["id"]

        async with AsyncSessionLocal() as s:
            eval_scores = (
                (
                    await s.execute(
                        select(Score).where(Score.source == "eval")
                    )
                )
                .scalars()
                .all()
            )
            assert len(eval_scores) == 3
            assert all(
                f"dataset_run_id={run_id}" in (sc.comment or "")
                for sc in eval_scores
            )
            assert all(sc.name.startswith("dataset_run:") for sc in eval_scores)
    finally:
        llm_factory.set_for_test(None)


async def test_list_runs_and_items(
    client: AsyncClient, admin_token: str, seeded_dataset: dict
):
    from chameleon.core.components.llms import factory as llm_factory

    llm_factory.set_for_test(_MockLLM("Answer #0"))  # type: ignore[arg-type]
    try:
        rr = await client.post(
            f"/v1/admin/datasets/{seeded_dataset['dataset_id']}/run",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "list-test", "judge": "contains"},
        )
        run_id = rr.json()["data"]["id"]

        # list runs
        lr = await client.get(
            f"/v1/admin/datasets/{seeded_dataset['dataset_id']}/runs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        runs = lr.json()["data"]
        assert run_id in [r["id"] for r in runs]

        # list run items
        ir = await client.get(
            f"/v1/admin/datasets/runs/{run_id}/items",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        items = ir.json()["data"]
        assert len(items) == 3
        assert all(it["actual_output"] is not None for it in items)
    finally:
        llm_factory.set_for_test(None)


async def test_compare_runs_returns_cells(
    client: AsyncClient, admin_token: str, seeded_dataset: dict
):
    """跑两个 run；对比返 item × run 表"""
    from chameleon.core.components.llms import factory as llm_factory

    # 第一个 run 用 "wrong"
    llm_factory.set_for_test(_MockLLM("wrong"))  # type: ignore[arg-type]
    r1 = await client.post(
        f"/v1/admin/datasets/{seeded_dataset['dataset_id']}/run",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "run-a", "judge": "contains"},
    )
    rid1 = r1.json()["data"]["id"]
    # 第二个 run 用 "Answer #0"
    llm_factory.set_for_test(_MockLLM("Answer #0"))  # type: ignore[arg-type]
    r2 = await client.post(
        f"/v1/admin/datasets/{seeded_dataset['dataset_id']}/run",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "run-b", "judge": "contains"},
    )
    rid2 = r2.json()["data"]["id"]
    llm_factory.set_for_test(None)

    cr = await client.post(
        "/v1/admin/datasets/runs/compare",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"run_ids": [rid1, rid2]},
    )
    assert cr.status_code == 200, cr.text
    result = cr.json()["data"]
    assert len(result["runs"]) == 2
    assert len(result["rows"]) == 3  # 3 个 item
    for row in result["rows"]:
        # 每行有 2 个 run 的 cell
        assert str(rid1) in row["cells"] or rid1 in row["cells"]


async def test_compare_runs_rejects_cross_dataset(
    client: AsyncClient, admin_token: str, seeded_dataset: dict
):
    """对比不同 dataset 下的 runs → 拒绝"""
    # 建另一个 dataset
    cr = await client.post(
        "/v1/admin/datasets",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "other"},
    )
    other_did = cr.json()["data"]["id"]
    # 给 other 加一条 item 才能 run
    async with AsyncSessionLocal() as s:
        s.add(
            DatasetItem(
                dataset_id=other_did,
                input_payload={"user_input": {"preview": "Q?"}},
            )
        )
        await s.commit()

    from chameleon.core.components.llms import factory as llm_factory

    llm_factory.set_for_test(_MockLLM("anything"))  # type: ignore[arg-type]
    r1 = await client.post(
        f"/v1/admin/datasets/{seeded_dataset['dataset_id']}/run",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "run-ds1", "judge": "contains"},
    )
    r2 = await client.post(
        f"/v1/admin/datasets/{other_did}/run",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "run-ds2", "judge": "contains"},
    )
    llm_factory.set_for_test(None)

    rid1 = r1.json()["data"]["id"]
    rid2 = r2.json()["data"]["id"]
    cmp_r = await client.post(
        "/v1/admin/datasets/runs/compare",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"run_ids": [rid1, rid2]},
    )
    body = cmp_r.json()
    assert body["success"] is False
    assert "同 dataset" in body["message"]
