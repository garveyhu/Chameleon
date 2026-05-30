"""record_scope 切面单测——注册假 sink，验证观测自动落库、归属/嵌套/计时正确。"""

from __future__ import annotations

import pytest

from chameleon.core.observe.context import (
    ObservationType,
    TraceContext,
    observe,
    reset_trace_context,
    set_trace_context,
)
from chameleon.core.observe.sink import set_observation_sink


@pytest.fixture
def captured(monkeypatch):
    """注册假 sink，收集落库字段；绕过 AsyncSessionLocal（用假 session）。"""
    rows: list[dict] = []

    async def fake_sink(session, **fields):
        rows.append(fields)

    set_observation_sink(fake_sink)

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def commit(self):
            pass

    # aspect._persist 内部 lazy import AsyncSessionLocal —— patch 成假的
    import chameleon.data.infra.db as db_mod

    monkeypatch.setattr(db_mod, "AsyncSessionLocal", lambda: _FakeSession())
    yield rows
    set_observation_sink(None)


async def test_record_scope_persists_retriever(captured):
    from chameleon.integrations.observe.aspect import record_scope

    token = set_trace_context(
        TraceContext(request_id="req-1", channel="api", app_id="app-x", agent_key="ag-x")
    )
    try:
        async with record_scope(
            observation_type=ObservationType.RETRIEVER,
            name="search_kb",
            request_payload={"query": "hi", "top_k": 3},
        ) as scope:
            scope.response_payload = {"hit_count": 2, "citations": [{"source": "kb1"}]}
    finally:
        reset_trace_context(token)

    assert len(captured) == 1
    row = captured[0]
    assert row["observation_type"] == "retriever"
    assert row["app_id"] == "app-x"
    assert row["agent_key"] == "ag-x"
    assert row["channel"] == "api"
    assert row["success"] is True
    assert row["request_payload"]["query"] == "hi"
    assert row["response_payload"]["hit_count"] == 2
    assert row["duration_ms"] >= 0


async def test_record_scope_nests_under_parent(captured):
    """父 observe scope 下的 record_scope 应挂到父 id。"""
    from chameleon.integrations.observe.aspect import record_scope

    token = set_trace_context(TraceContext(request_id="req-2", app_id="a", agent_key="g"))
    try:
        async with observe(observation_type=ObservationType.SPAN, request_id="parent-span"):
            async with record_scope(observation_type=ObservationType.RETRIEVER):
                pass
    finally:
        reset_trace_context(token)

    assert captured[0]["parent_id"] == "parent-span"


async def test_record_scope_marks_error(captured):
    from chameleon.integrations.observe.aspect import record_scope

    token = set_trace_context(TraceContext(request_id="req-3", app_id="a", agent_key="g"))
    try:
        with pytest.raises(ValueError):
            async with record_scope(observation_type=ObservationType.TOOL):
                raise ValueError("boom")
    finally:
        reset_trace_context(token)

    assert captured[0]["success"] is False
    assert captured[0]["observation_type"] == "tool"
    assert "boom" in captured[0]["error_message"]


async def test_record_scope_no_trace_context_falls_back(captured):
    """无 TraceContext 时兜底 internal，仍落库。"""
    from chameleon.integrations.observe.aspect import record_scope

    async with record_scope(observation_type=ObservationType.EMBEDDING):
        pass

    assert captured[0]["app_id"] == "internal"
    assert captured[0]["channel"] == "internal"
