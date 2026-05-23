"""P22.2 PR #73 E2E：OTLP HTTP 摄入端点"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import ApiKey, App, CallLog
from chameleon.system.api_key.schemas import CreateApiKeyRequest
from chameleon.system.api_key.service import create_api_key
from chameleon.system.pricing import seed_default_pricing


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _seed_pricing():
    async with AsyncSessionLocal() as s:
        await seed_default_pricing(s)
        await s.commit()


@pytest_asyncio.fixture
async def app_with_key():
    suffix = secrets.token_hex(3)
    app_key = f"e2e-otel-{suffix}"
    async with AsyncSessionLocal() as s:
        s.add(App(app_key=app_key, name="otel test", status="active"))
        await s.commit()
        rec = await create_api_key(
            s,
            CreateApiKeyRequest(
                app_id=app_key, name="t", scopes=[], description=None
            ),
        )
        await s.commit()
    yield {"app_key": app_key, "api_key": rec.plain_key}
    async with AsyncSessionLocal() as s:
        await s.execute(delete(CallLog).where(CallLog.app_id == app_key))
        await s.execute(delete(ApiKey).where(ApiKey.app_id == app_key))
        await s.execute(delete(App).where(App.app_key == app_key))
        await s.commit()


def _hdr(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _make_otlp_payload(
    *, trace_id: str, span_id: str, parent_span_id: str | None = None,
    name: str = "openai.chat.completion",
    model: str | None = "gpt-4o-mini",
    prompt_tokens: int | None = 100,
    completion_tokens: int | None = 50,
    is_error: bool = False,
) -> dict:
    attrs = []
    if model:
        attrs.append({"key": "gen_ai.request.model", "value": {"stringValue": model}})
        attrs.append({"key": "gen_ai.system", "value": {"stringValue": "openai"}})
    if prompt_tokens is not None:
        attrs.append({
            "key": "gen_ai.usage.prompt_tokens",
            "value": {"intValue": str(prompt_tokens)},
        })
    if completion_tokens is not None:
        attrs.append({
            "key": "gen_ai.usage.completion_tokens",
            "value": {"intValue": str(completion_tokens)},
        })
    span: dict = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "kind": 3,
        "startTimeUnixNano": "1700000000000000000",
        "endTimeUnixNano":   "1700000000500000000",  # 500ms
        "attributes": attrs,
        "status": {"code": 2 if is_error else 1},
    }
    if parent_span_id:
        span["parentSpanId"] = parent_span_id
    return {
        "resourceSpans": [
            {
                "resource": {"attributes": []},
                "scopeSpans": [
                    {
                        "scope": {"name": "openai-instrument", "version": "1.0"},
                        "spans": [span],
                    }
                ],
            }
        ]
    }


# ── 基础摄入 ────────────────────────────────────────────


async def test_export_traces_basic(
    client: AsyncClient, app_with_key: dict
):
    payload = _make_otlp_payload(
        trace_id="a" * 32, span_id="b" * 16, model="gpt-4o-mini",
        prompt_tokens=200, completion_tokens=100,
    )
    r = await client.post(
        "/v1/otel/v1/traces",
        headers=_hdr(app_with_key["api_key"]),
        json=payload,
    )
    assert r.status_code == 200, r.text

    # 验证 call_log 写入
    async with AsyncSessionLocal() as s:
        log = (
            await s.execute(
                select(CallLog).where(
                    CallLog.app_id == app_with_key["app_key"]
                )
            )
        ).scalar_one_or_none()
        assert log is not None
        assert log.observation_type == "generation"
        assert log.prompt_tokens == 200
        assert log.completion_tokens == 100
        assert log.total_tokens == 300
        assert log.success is True
        assert log.duration_ms == 500
        assert log.parent_id is None  # 没 parent_span_id
        # cost_usd 自动算（gpt-4o-mini 价目已 seed）
        assert log.cost_usd is not None
        assert float(log.cost_usd) > 0


async def test_export_traces_nested_span(
    client: AsyncClient, app_with_key: dict
):
    """parent_span 在前，child 引 parentSpanId"""
    tid = "c" * 32
    parent_id = "d" * 16
    child_id = "e" * 16

    parent_payload = _make_otlp_payload(
        trace_id=tid, span_id=parent_id, name="agent.run",
    )
    child_payload = _make_otlp_payload(
        trace_id=tid, span_id=child_id, parent_span_id=parent_id,
        name="openai.chat.completion",
    )
    for p in (parent_payload, child_payload):
        r = await client.post(
            "/v1/otel/v1/traces",
            headers=_hdr(app_with_key["api_key"]),
            json=p,
        )
        assert r.status_code == 200

    async with AsyncSessionLocal() as s:
        logs = (
            await s.execute(
                select(CallLog).where(
                    CallLog.app_id == app_with_key["app_key"]
                )
            )
        ).scalars().all()
        assert len(logs) == 2
        # parent log 的 parent_id 为 NULL
        # child log 的 parent_id 应该是 trace-parent_span 拼
        children = [lg for lg in logs if lg.parent_id is not None]
        assert len(children) == 1
        assert parent_id in children[0].parent_id


async def test_export_traces_error_status(
    client: AsyncClient, app_with_key: dict
):
    payload = _make_otlp_payload(
        trace_id="f" * 32, span_id="0" * 16, is_error=True,
    )
    payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["status"][
        "message"
    ] = "rate limit"
    r = await client.post(
        "/v1/otel/v1/traces",
        headers=_hdr(app_with_key["api_key"]),
        json=payload,
    )
    assert r.status_code == 200
    async with AsyncSessionLocal() as s:
        log = (
            await s.execute(
                select(CallLog).where(
                    CallLog.app_id == app_with_key["app_key"]
                )
            )
        ).scalar_one()
        assert log.success is False
        assert "rate" in log.error_message


# ── 鉴权 ───────────────────────────────────────────────


async def test_export_traces_without_auth_rejected(client: AsyncClient):
    payload = _make_otlp_payload(trace_id="1" * 32, span_id="2" * 16)
    r = await client.post("/v1/otel/v1/traces", json=payload)
    # 红线：必须有 app_id 校验（401 或 403）
    assert r.status_code in (401, 403)


async def test_export_traces_with_bad_token_rejected(client: AsyncClient):
    payload = _make_otlp_payload(trace_id="1" * 32, span_id="2" * 16)
    r = await client.post(
        "/v1/otel/v1/traces",
        headers={"Authorization": "Bearer not-a-real-key-12345"},
        json=payload,
    )
    assert r.status_code in (401, 403)


# ── 边界 ───────────────────────────────────────────────


async def test_export_traces_empty(client: AsyncClient, app_with_key: dict):
    r = await client.post(
        "/v1/otel/v1/traces",
        headers=_hdr(app_with_key["api_key"]),
        json={"resourceSpans": []},
    )
    assert r.status_code == 200


async def test_export_traces_too_many_rejected(
    client: AsyncClient, app_with_key: dict
):
    # 构造 > 5000 span
    spans = [
        {
            "traceId": "1" * 32,
            "spanId": format(i, "016x"),
            "name": "s",
            "kind": 1,
            "startTimeUnixNano": "1700000000000000000",
            "endTimeUnixNano": "1700000000100000000",
            "attributes": [],
            "status": {"code": 1},
        }
        for i in range(5001)
    ]
    payload = {
        "resourceSpans": [
            {
                "resource": {"attributes": []},
                "scopeSpans": [{"scope": None, "spans": spans}],
            }
        ]
    }
    r = await client.post(
        "/v1/otel/v1/traces",
        headers=_hdr(app_with_key["api_key"]),
        json=payload,
    )
    assert r.status_code == 413
