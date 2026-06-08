"""OTel 出站映射单测：call_log 行 → OTLP/HTTP JSON（GenAI semconv）。"""

from __future__ import annotations

import types

import pytest

from chameleon.integrations.otel_export import build_otlp_payload


def _attrs(span):
    return {a["key"]: a["value"] for a in span["attributes"]}


def test_build_otlp_payload_structure_and_genai_mapping():
    rows = [
        {
            "request_id": "root1", "parent_id": None, "observation_type": "trace",
            "name": "invoke", "model_code": "qwen-plus", "prompt_tokens": 90,
            "completion_tokens": 2, "total_tokens": 92, "cost_usd": 0.000125,
            "duration_ms": 1200, "channel": "openai", "agent_key": "demo",
            "success": True, "start_unix_nano": 1_000_000_000_000_000_000,
        },
        {
            "request_id": "gen1", "parent_id": "root1", "observation_type": "generation",
            "name": "llm", "model_code": "qwen-plus", "prompt_tokens": 90,
            "completion_tokens": 2, "total_tokens": 92, "cost_usd": 0.000125,
            "duration_ms": 1100, "channel": "openai", "agent_key": "demo",
            "success": True, "start_unix_nano": 1_000_000_000_100_000_000,
        },
    ]
    payload = build_otlp_payload("root1", rows)
    spans = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert len(spans) == 2
    root, gen = spans[0], spans[1]

    # 同一 trace 共享 traceId；root 无 parentSpanId，子 span parent 指向 root span
    assert root["traceId"] == gen["traceId"]
    assert "parentSpanId" not in root
    assert gen["parentSpanId"] == root["spanId"]
    # id 是合法 hex（trace 32 / span 16）
    assert len(root["traceId"]) == 32 and len(root["spanId"]) == 16

    # GenAI semconv 属性映射
    a = _attrs(gen)
    assert a["gen_ai.usage.input_tokens"] == {"intValue": "90"}
    assert a["gen_ai.usage.total_tokens"] == {"intValue": "92"}
    assert a["gen_ai.usage.cost"] == {"doubleValue": 0.000125}
    assert a["gen_ai.request.model"] == {"stringValue": "qwen-plus"}
    assert a["gen_ai.system"] == {"stringValue": "qwen-plus"}  # generation 才有 system
    # trace 行无 gen_ai.system
    assert "gen_ai.system" not in _attrs(root)

    # 时间：end = start + duration*1e6
    assert int(gen["endTimeUnixNano"]) == 1_000_000_000_100_000_000 + 1100 * 1_000_000


def test_build_otlp_payload_marks_error_status():
    rows = [{
        "request_id": "r", "parent_id": None, "observation_type": "trace",
        "name": "x", "success": False, "error_message": "boom",
        "duration_ms": 5, "start_unix_nano": 1,
    }]
    span = build_otlp_payload("r", rows)["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert span["status"]["code"] == 2 and span["status"]["message"] == "boom"


@pytest.mark.asyncio
async def test_export_trace_posts_payload_to_endpoint(monkeypatch):
    """export_trace 真出站路径（声明审计缺口）：查 trace 行→构 OTLP→httpx POST 到 endpoint。

    mock DB（返假 CallLog）+ mock httpx，验 payload 被 POST 到配置的 endpoint。
    """
    import datetime as _dt

    from chameleon.integrations.otel_export import exporter

    monkeypatch.setattr(exporter, "export_endpoint", lambda: "http://collector:4318/v1/traces")

    # 假 CallLog 行（根 + 一条 generation 子行）
    def _row(rid, parent, otype, model=None, tokens=None):
        return types.SimpleNamespace(
            request_id=rid, parent_id=parent, observation_type=otype,
            name=otype, model_code=model, prompt_tokens=None, completion_tokens=None,
            total_tokens=tokens, cost_usd=None, duration_ms=12, channel="agent",
            agent_key="a", success=True, error_message=None,
            created_at=_dt.datetime(2026, 6, 8, tzinfo=_dt.timezone.utc),
        )

    fake_logs = [_row("root", None, "trace"), _row("root.1", "root", "generation", "gpt", 42)]

    class _Scalars:
        def all(self):
            return fake_logs

    class _Result:
        def scalars(self):
            return _Scalars()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, *a, **k):
            return _Result()

    monkeypatch.setattr(
        "chameleon.data.infra.db.AsyncSessionLocal", lambda: _Session()
    )

    posted: dict = {}

    class _Resp:
        status_code = 200

    class _Client:
        def __init__(self, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json, headers):
            posted["url"] = url
            posted["payload"] = json
            return _Resp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    await exporter.export_trace("root")

    assert posted["url"] == "http://collector:4318/v1/traces"
    # OTLP/HTTP JSON 结构 + 两个 span（trace 根 + generation）真被 POST 出去
    spans = posted["payload"]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert len(spans) == 2
