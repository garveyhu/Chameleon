"""SSE event helpers + payload 模型 单测

确保 wire format 与现有客户端兼容：每个 helper 产出顶层 key 与 SSEEventKind
对应，payload shape 与 frontend TS 镜像一致。
"""

from __future__ import annotations

import pytest

from chameleon.core.api.sse_events import (
    CitationPayload,
    ErrorPayload,
    NodePayload,
    SSEEventKind,
    ThoughtPayload,
    UsagePayload,
    event_citation,
    event_delta,
    event_end,
    event_error,
    event_meta,
    event_node_end,
    event_node_start,
    event_thought,
    event_usage,
)

# ── 共享 payload ────────────────────────────────────────────


def test_usage_payload_from_dict():
    u = UsagePayload.from_dict({"input_tokens": 10, "output_tokens": 20})
    assert u is not None
    assert u.input_tokens == 10
    assert u.output_tokens == 20
    assert u.total_tokens == 0


def test_usage_payload_from_none():
    assert UsagePayload.from_dict(None) is None
    assert UsagePayload.from_dict({}) is None


def test_citation_payload_extra_allowed():
    """RAG citation 支持业务自定义字段（page / char_range 等）"""
    c = CitationPayload(source="kb", page=5, char_range=[100, 200])
    dumped = c.model_dump(exclude_none=True)
    assert dumped["source"] == "kb"
    assert dumped["page"] == 5
    assert dumped["char_range"] == [100, 200]


# ── 事件 builder ────────────────────────────────────────────


def test_event_meta_flat_dict():
    e = event_meta(agent="echo", session_id="abc")
    assert e == {"meta": {"agent": "echo", "session_id": "abc"}}


def test_event_delta_string_only():
    e = event_delta("hello")
    assert e == {"delta": "hello"}


def test_event_citation_pydantic():
    payload = CitationPayload(source="kb", title="t")
    e = event_citation(payload)
    assert e["citation"]["source"] == "kb"
    assert e["citation"]["title"] == "t"
    # snippet None 应该被 exclude
    assert "snippet" not in e["citation"]


def test_event_citation_raw_dict():
    e = event_citation({"source": "kb", "custom_field": 42})
    assert e["citation"]["source"] == "kb"
    assert e["citation"]["custom_field"] == 42


def test_event_end_with_usage_pydantic():
    u = UsagePayload(input_tokens=10, output_tokens=20, total_tokens=30)
    e = event_end(usage=u, latency_ms=120, answer="hello")
    assert e["end"] is True
    assert e["usage"] == {
        "input_tokens": 10,
        "output_tokens": 20,
        "total_tokens": 30,
    }
    assert e["latency_ms"] == 120
    assert e["answer"] == "hello"


def test_event_end_with_usage_none():
    """usage 显式 None 也要出现在 dict 中（前端要区分 None vs 未上报）"""
    e = event_end(usage=None, latency_ms=50)
    assert e["end"] is True
    assert "usage" in e
    assert e["usage"] is None
    assert e["latency_ms"] == 50


def test_event_end_with_raw_usage_dict():
    e = event_end(usage={"input_tokens": 5})
    assert e["usage"] == {"input_tokens": 5}


def test_event_error_from_exception():
    e = event_error(ValueError("bad input"))
    assert e["error"]["type"] == "ValueError"
    assert e["error"]["message"] == "bad input"


def test_event_error_from_type_string():
    e = event_error("ConfigError", "missing base_url")
    assert e["error"]["type"] == "ConfigError"
    assert e["error"]["message"] == "missing base_url"


def test_event_error_message_truncate():
    long_msg = "x" * 500
    e = event_error("X", long_msg)
    assert len(e["error"]["message"]) == 300


def test_event_error_exception_message_truncate():
    long_msg = "y" * 500
    e = event_error(RuntimeError(long_msg))
    assert len(e["error"]["message"]) == 300


def test_event_error_string_without_message_fallback():
    e = event_error("Unknown")
    assert e["error"]["type"] == "Unknown"
    assert e["error"]["message"] == "unknown error"


def test_event_usage_standalone():
    u = UsagePayload(input_tokens=1, output_tokens=2, total_tokens=3)
    e = event_usage(u)
    # usage 顶层 key（与 end 区分）
    assert "usage" in e
    assert "end" not in e
    assert e["usage"]["input_tokens"] == 1


def test_event_thought_pydantic():
    e = event_thought(ThoughtPayload(step=1, tool="search", input={"q": "foo"}))
    assert e["thought"]["step"] == 1
    assert e["thought"]["tool"] == "search"


def test_event_node_start_end():
    p = NodePayload(node_id="n1", node_type="llm", name="LLM 节点")
    assert event_node_start(p)["node_start"]["node_id"] == "n1"
    p2 = NodePayload(node_id="n1", status="ok", duration_ms=120)
    assert event_node_end(p2)["node_end"]["status"] == "ok"


# ── SSEEventKind 与 wire key 对齐 ─────────────────────────


@pytest.mark.parametrize(
    "kind,builder,args",
    [
        (SSEEventKind.META, lambda: event_meta(a=1), ()),
        (SSEEventKind.DELTA, lambda: event_delta("x"), ()),
        (SSEEventKind.CITATION, lambda: event_citation({}), ()),
        (SSEEventKind.END, lambda: event_end(), ()),
        (SSEEventKind.ERROR, lambda: event_error("E", "m"), ()),
        (SSEEventKind.USAGE, lambda: event_usage(UsagePayload()), ()),
        (SSEEventKind.THOUGHT, lambda: event_thought({"step": 0}), ()),
        (SSEEventKind.NODE_START, lambda: event_node_start({"node_id": "n"}), ()),
        (SSEEventKind.NODE_END, lambda: event_node_end({"node_id": "n"}), ()),
    ],
)
def test_event_kind_matches_wire_key(kind, builder, args):
    """每个 builder 产出 dict 的顶层 key 必须等于 SSEEventKind 字符串"""
    out = builder()
    assert kind.value in out


def test_error_payload_validation():
    # type/message 必填
    with pytest.raises(Exception):
        ErrorPayload()
