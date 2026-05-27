"""P22.2 PR #74 E2E：Python SDK 端到端打到 backend OTLP 端点"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import ApiKey, CallLog
from chameleon.system.api_key.schemas import CreateApiKeyRequest
from chameleon.system.api_key.service import create_api_key
from chameleon.system.pricing import seed_default_pricing

# 把 sdk/python 加入 sys.path
_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk" / "python"
if str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from chameleon_sdk import AsyncClient as ChameleonAsyncClient
from chameleon_sdk import Client  # noqa: E402


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _seed_pricing():
    async with AsyncSessionLocal() as s:
        await seed_default_pricing(s)
        await s.commit()


@pytest_asyncio.fixture
async def app_with_key():
    suffix = secrets.token_hex(3)
    app_key = f"e2e-sdk-{suffix}"
    async with AsyncSessionLocal() as s:
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
        await s.commit()


# ── SDK 通过 httpx 内打 ASGITransport（直连 FastAPI app）─────────


class _AsgiClient(Client):
    """子类化 Client，让它通过 ASGITransport 直连 FastAPI app（不依赖网络）"""

    def __init__(self, *, httpx_client, **kw):
        super().__init__(**kw)
        self._http = httpx_client  # 注入测试用的 httpx async client


def test_python_sdk_init_requires_api_key():
    import os
    os.environ.pop("CHAMELEON_API_KEY", None)
    with pytest.raises(ValueError):
        Client()


def test_python_sdk_init_with_env_var(monkeypatch):
    monkeypatch.setenv("CHAMELEON_API_KEY", "env-key")
    c = Client()
    assert c.api_key == "env-key"


def test_python_sdk_endpoint_url():
    c = Client(api_key="x", base_url="http://example.com/")
    assert c.traces_endpoint == "http://example.com/v1/otel/v1/traces"


# ── Trace + Span ────────────────────────────────────────────


def test_python_sdk_trace_buffers_spans():
    c = Client(api_key="x", base_url="http://example.com")
    with c.trace(name="t1") as t:
        with t.span("step1", observation_type="generation") as sp:
            sp.set_model("gpt-4o-mini")
            sp.set_usage(prompt_tokens=100, completion_tokens=50)
        with t.span("step2", observation_type="tool"):
            pass
    # buffer 应该有 3 个 spans（trace root + 2 children）
    assert len(c._buffer) == 3


def test_python_sdk_span_parent_chain():
    c = Client(api_key="x", base_url="http://example.com")
    with c.trace(name="root") as t:
        with t.span("a") as a:
            with t.span("b") as b:
                _ = a, b
    # 找到 root / a / b
    span_by_name = {sp["name"]: sp for sp in c._buffer}
    assert "root" in span_by_name and "a" in span_by_name and "b" in span_by_name
    # a 的 parent 是 root；b 的 parent 是 a
    root_id = span_by_name["root"]["spanId"]
    a_id = span_by_name["a"]["spanId"]
    assert span_by_name["a"].get("parentSpanId") == root_id
    assert span_by_name["b"].get("parentSpanId") == a_id


def test_python_sdk_span_status_on_exception():
    c = Client(api_key="x", base_url="http://example.com")
    try:
        with c.trace(name="t") as t:
            with t.span("boom"):
                raise RuntimeError("oops")
    except RuntimeError:
        pass
    by_name = {sp["name"]: sp for sp in c._buffer}
    assert by_name["boom"]["status"]["code"] == 2
    assert "oops" in by_name["boom"]["status"]["message"]


def test_python_sdk_span_attributes_serialized():
    c = Client(api_key="x", base_url="http://example.com")
    with c.trace() as t:
        with t.span("step1") as sp:
            sp.set_attribute("custom", "value")
            sp.set_attribute("count", 42)
            sp.set_attribute("flag", True)
            sp.set_attribute("ratio", 0.5)
    by_name = {sp["name"]: sp for sp in c._buffer}
    attrs = {a["key"]: a["value"] for a in by_name["step1"]["attributes"]}
    assert attrs["custom"]["stringValue"] == "value"
    assert int(attrs["count"]["intValue"]) == 42
    assert attrs["flag"]["boolValue"] is True
    assert attrs["ratio"]["doubleValue"] == 0.5


# ── 通过 ASGI client 端到端上报到 backend ────────────────


async def test_python_sdk_e2e_via_asgi(
    client: AsyncClient, app_with_key: dict
):
    """构造 SDK payload → 通过 ASGITransport 打 backend → 验证 call_logs 写入"""
    sdk_client = Client(
        api_key=app_with_key["api_key"], base_url="http://test"
    )
    with sdk_client.trace(name="sdk-trace") as t:
        with t.span("retrieve", observation_type="retriever") as sp:
            sp.set_attribute("kb_id", "smoke")
        with t.span("llm", observation_type="generation") as sp:
            sp.set_model("gpt-4o-mini")
            sp.set_usage(prompt_tokens=200, completion_tokens=100)

    # 取 payload 用 ASGI client 上报（避免真实网络）
    payload = sdk_client._drain_payload()
    assert payload is not None
    r = await client.post(
        "/v1/otel/v1/traces",
        headers={"Authorization": f"Bearer {app_with_key['api_key']}"},
        json=payload,
    )
    assert r.status_code == 200, r.text

    async with AsyncSessionLocal() as s:
        logs = (
            await s.execute(
                select(CallLog).where(
                    CallLog.app_id == app_with_key["app_key"]
                )
            )
        ).scalars().all()
        assert len(logs) == 3  # root trace + retrieve + llm
        gen_log = [lg for lg in logs if lg.observation_type == "generation"][0]
        assert gen_log.prompt_tokens == 200
        assert gen_log.completion_tokens == 100
        # cost_usd 自动算
        assert gen_log.cost_usd is not None
        assert float(gen_log.cost_usd) > 0


# AsyncClient smoke：保证类能实例化
def test_python_sdk_async_client_constructs():
    c = ChameleonAsyncClient(api_key="x", base_url="http://example.com")
    assert c.api_key == "x"


# ── @trace decorator + patch_openai ─────────────────────


def test_trace_decorator_wraps_function():
    from chameleon_sdk import set_default_client
    from chameleon_sdk import trace as trace_deco

    c = Client(api_key="x", base_url="http://example.com")
    set_default_client(c)

    @trace_deco(name="job-1")
    def my_job(x):
        return x * 2

    result = my_job(21)
    assert result == 42
    # buffer 应该有 trace root span
    assert len(c._buffer) >= 1
    assert c._buffer[0]["name"] == "job-1"


def test_get_default_client_raises_when_unset():
    import chameleon_sdk.decorators as deco_module
    deco_module._default_client = None
    with pytest.raises(RuntimeError, match="default Client"):
        deco_module.get_default_client()


def test_patch_all_silent_when_openai_missing():
    """patch_all 在 openai 未装时不抛错，仅静默跳过"""
    import chameleon_sdk.decorators as deco
    from chameleon_sdk import patch_all

    c = Client(api_key="x", base_url="http://example.com")
    original_patch = deco.patch_openai

    def fake_patch_openai(_):
        raise RuntimeError("openai package not installed")

    deco.patch_openai = fake_patch_openai
    try:
        patch_all(c)  # 不应抛
    finally:
        deco.patch_openai = original_patch
