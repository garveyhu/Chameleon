"""P19.1 PR #31 E2E：alert pipeline + regression threshold + Redis dedup

策略：
- mock datasets.runner.run_dataset 控制 mean_score
- 用 respx 拦截 Slack / Webhook HTTP，验证 alert 实际发出
- 显式清 Redis dedup key，避免测试相互污染
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.data.infra import redis as redis_infra
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
from chameleon.system.eval_jobs.alert import should_alert
from chameleon.system.seed.runner import run_seed_if_empty

# ── 纯单元 ───────────────────────────────────────────────


def test_should_alert_no_config():
    assert should_alert(None, Decimal("-0.5")) is False
    assert should_alert({}, Decimal("-0.5")) is False
    assert should_alert({"kind": ""}, Decimal("-0.5")) is False


def test_should_alert_no_threshold():
    cfg = {"kind": "slack", "target": "x"}
    assert should_alert(cfg, Decimal("-0.5")) is False
    cfg2 = {"kind": "slack", "target": "x", "regression_threshold": 0}
    assert should_alert(cfg2, Decimal("-0.5")) is False


def test_should_alert_no_delta():
    cfg = {"kind": "slack", "target": "x", "regression_threshold": 0.1}
    assert should_alert(cfg, None) is False


def test_should_alert_below_threshold():
    cfg = {"kind": "slack", "target": "x", "regression_threshold": 0.1}
    assert should_alert(cfg, Decimal("-0.05")) is False  # 跌 5% < 10%


def test_should_alert_fires_on_drop():
    cfg = {"kind": "slack", "target": "x", "regression_threshold": 0.1}
    assert should_alert(cfg, Decimal("-0.15")) is True


def test_should_alert_does_not_fire_on_improvement():
    cfg = {"kind": "slack", "target": "x", "regression_threshold": 0.1}
    assert should_alert(cfg, Decimal("0.2")) is False  # 涨 20% 不发警


# ── fixtures ────────────────────────────────────────────


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-ea-{rand}"
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


_SLACK_URL = "https://hooks.slack.example/services/T/B/X"
_WEBHOOK_URL = "https://example.test/eval-alert"


def _alert_cfg(kind: str, target: str, threshold: float = 0.1, silence_min: int = 60):
    return {
        "kind": kind,
        "target": target,
        "regression_threshold": threshold,
        "silence_minutes": silence_min,
    }


@pytest_asyncio.fixture
async def job_with_alert(admin_token: str, client: AsyncClient):
    """带 Slack alert 配的 job"""
    async with AsyncSessionLocal() as s:
        ds = Dataset(name=f"alert-ds-{secrets.token_hex(2)}", item_count=1)
        s.add(ds)
        await s.commit()
        await s.refresh(ds)
        did = ds.id

    r = await client.post(
        "/v1/admin/eval-jobs",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "job_key": f"alert-job-{secrets.token_hex(2)}",
            "name": "alert test",
            "dataset_id": did,
            "cron_expr": "0 0 * * *",
            "judge": "exact_match",
            "alert_config": _alert_cfg("slack", _SLACK_URL),
        },
    )
    assert r.status_code == 200
    jid = r.json()["data"]["id"]

    # 清理可能残留的 dedup key
    for kind in ("slack", "webhook"):
        try:
            await redis_infra.get_redis().delete(f"eval_alert:{jid}:{kind}")
        except Exception:
            pass

    yield jid

    async with AsyncSessionLocal() as s:
        await s.execute(delete(EvalJobRun).where(EvalJobRun.job_id == jid))
        await s.execute(delete(EvalJob).where(EvalJob.id == jid))
        await s.execute(delete(DatasetRun).where(DatasetRun.dataset_id == did))
        await s.execute(delete(Dataset).where(Dataset.id == did))
        await s.commit()
    for kind in ("slack", "webhook"):
        try:
            await redis_infra.get_redis().delete(f"eval_alert:{jid}:{kind}")
        except Exception:
            pass


def _make_fake_runner(mean_score: float):
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


# ── 整链路 ──────────────────────────────────────────────


async def test_alert_fires_slack_on_regression(
    client: AsyncClient,
    admin_token: str,
    job_with_alert: int,
    monkeypatch: pytest.MonkeyPatch,
    respx_mock,
):
    """两次触发：第二次跌 30% 应触发 Slack 调用 + alert_sent=True"""
    # 第一次：基线 0.80
    monkeypatch.setattr(
        "chameleon.system.eval_jobs.service.ds_runner.run_dataset",
        _make_fake_runner(0.80),
    )
    await client.post(
        f"/v1/admin/eval-jobs/{job_with_alert}/trigger",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # 第二次：0.50，跌 30% > 阈值 10%
    monkeypatch.setattr(
        "chameleon.system.eval_jobs.service.ds_runner.run_dataset",
        _make_fake_runner(0.50),
    )
    route = respx_mock.post(_SLACK_URL).mock(
        return_value=httpx.Response(200, text="ok")
    )

    r = await client.post(
        f"/v1/admin/eval-jobs/{job_with_alert}/trigger",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    assert route.called

    # 最新 run 的 alert_sent=True
    runs_r = await client.get(
        f"/v1/admin/eval-jobs/{job_with_alert}/runs",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    latest = runs_r.json()["data"][0]
    assert latest["alert_sent"] is True
    assert latest["alert_target"] == _SLACK_URL


async def test_alert_below_threshold_not_sent(
    client: AsyncClient,
    admin_token: str,
    job_with_alert: int,
    monkeypatch: pytest.MonkeyPatch,
    respx_mock,
):
    """跌幅 5% < 10% 阈值，不应该发送"""
    monkeypatch.setattr(
        "chameleon.system.eval_jobs.service.ds_runner.run_dataset",
        _make_fake_runner(0.80),
    )
    await client.post(
        f"/v1/admin/eval-jobs/{job_with_alert}/trigger",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    monkeypatch.setattr(
        "chameleon.system.eval_jobs.service.ds_runner.run_dataset",
        _make_fake_runner(0.75),  # -0.05，跌幅 5%
    )
    route = respx_mock.post(_SLACK_URL).mock(
        return_value=httpx.Response(200, text="ok")
    )

    await client.post(
        f"/v1/admin/eval-jobs/{job_with_alert}/trigger",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert not route.called


async def test_alert_dedup_within_silence_period(
    client: AsyncClient,
    admin_token: str,
    job_with_alert: int,
    monkeypatch: pytest.MonkeyPatch,
    respx_mock,
):
    """连续两次跌破阈值，第二次应被 Redis dedup 静默"""
    monkeypatch.setattr(
        "chameleon.system.eval_jobs.service.ds_runner.run_dataset",
        _make_fake_runner(0.80),
    )
    await client.post(
        f"/v1/admin/eval-jobs/{job_with_alert}/trigger",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    route = respx_mock.post(_SLACK_URL).mock(
        return_value=httpx.Response(200, text="ok")
    )

    # 第二次：跌 30%（触发）
    monkeypatch.setattr(
        "chameleon.system.eval_jobs.service.ds_runner.run_dataset",
        _make_fake_runner(0.50),
    )
    await client.post(
        f"/v1/admin/eval-jobs/{job_with_alert}/trigger",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    first_call_count = route.call_count
    assert first_call_count == 1

    # 第三次：再跌（仍触发阈值，但应被静默期挡掉）
    monkeypatch.setattr(
        "chameleon.system.eval_jobs.service.ds_runner.run_dataset",
        _make_fake_runner(0.30),
    )
    await client.post(
        f"/v1/admin/eval-jobs/{job_with_alert}/trigger",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    # call_count 没增加
    assert route.call_count == first_call_count

    # 最新 run alert_sent=False（被 dedup）
    runs_r = await client.get(
        f"/v1/admin/eval-jobs/{job_with_alert}/runs",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    latest = runs_r.json()["data"][0]
    assert latest["alert_sent"] is False


async def test_alert_notifier_failure_doesnt_break_trigger(
    client: AsyncClient,
    admin_token: str,
    job_with_alert: int,
    monkeypatch: pytest.MonkeyPatch,
    respx_mock,
):
    """notifier 网络失败 → alert_sent=False，但 trigger 仍成功返回"""
    monkeypatch.setattr(
        "chameleon.system.eval_jobs.service.ds_runner.run_dataset",
        _make_fake_runner(0.80),
    )
    await client.post(
        f"/v1/admin/eval-jobs/{job_with_alert}/trigger",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # mock 500
    respx_mock.post(_SLACK_URL).mock(
        return_value=httpx.Response(500, text="server error")
    )

    monkeypatch.setattr(
        "chameleon.system.eval_jobs.service.ds_runner.run_dataset",
        _make_fake_runner(0.30),
    )
    r = await client.post(
        f"/v1/admin/eval-jobs/{job_with_alert}/trigger",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    # trigger 不该因 alert 失败而返错
    assert r.status_code == 200

    runs_r = await client.get(
        f"/v1/admin/eval-jobs/{job_with_alert}/runs",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    latest = runs_r.json()["data"][0]
    assert latest["alert_sent"] is False  # 发送失败 → 不标记


# ── notifier 单元 ───────────────────────────────────────


async def test_webhook_notifier_2xx_success(respx_mock):
    from chameleon.core.components.notifier import WebhookNotifier

    route = respx_mock.post(_WEBHOOK_URL).mock(
        return_value=httpx.Response(204)
    )
    sent = await WebhookNotifier().send(
        _WEBHOOK_URL, text="hi", payload={"job_id": 1}
    )
    assert sent is True
    assert route.called
    # body 含 source / level / text / payload
    req_body = route.calls[0].request.content.decode()
    assert "chameleon" in req_body
    assert "job_id" in req_body


async def test_slack_notifier_non_200(respx_mock):
    from chameleon.core.components.notifier import SlackNotifier

    respx_mock.post(_SLACK_URL).mock(
        return_value=httpx.Response(403, text="invalid_token")
    )
    sent = await SlackNotifier().send(_SLACK_URL, text="hi")
    assert sent is False
