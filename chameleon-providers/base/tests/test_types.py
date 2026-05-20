"""Provider types & 聚合器单测"""

from chameleon.providers.base.types import (
    AgentDef,
    Citation,
    InvokeContext,
    InvokeResult,
    Message,
    StepRecord,
    StreamEvent,
    StreamEventType,
    ToolCallRecord,
    Usage,
    _StreamAggregator,
)


def test_agent_def_basic() -> None:
    ad = AgentDef(
        key="sql-qa",
        provider="langgraph",
        description="SQL 问答",
        config={"module": "chameleon.agents.sql_qa"},
    )
    assert ad.key == "sql-qa"
    assert ad.provider == "langgraph"
    assert ad.config["module"] == "chameleon.agents.sql_qa"


def test_invoke_context_str_input() -> None:
    ctx = InvokeContext(
        agent_def=AgentDef(key="x", provider="langgraph"),
        input="hi",
        session_id="sess_abc",
        app_id="app1",
    )
    assert isinstance(ctx.input, str)


def test_invoke_context_messages_input() -> None:
    ctx = InvokeContext(
        agent_def=AgentDef(key="x", provider="langgraph"),
        input=[Message(role="user", content="hi")],
        session_id="sess_abc",
        app_id="app1",
    )
    assert isinstance(ctx.input, list)
    assert ctx.input[0].role == "user"


def test_stream_event_types_closed_enum() -> None:
    expected = {
        "delta",
        "step",
        "citation",
        "tool_call",
        "tool_result",
        "metadata",
        "done",
        "error",
    }
    assert {t.value for t in StreamEventType} == expected


def test_aggregator_delta_only() -> None:
    agg = _StreamAggregator(session_id="s", request_id="r")
    agg.feed(StreamEvent(type=StreamEventType.delta, data={"text": "今天"}))
    agg.feed(StreamEvent(type=StreamEventType.delta, data={"text": "销售额"}))
    result = agg.result()
    assert result.answer == "今天销售额"
    assert result.session_id == "s"
    assert result.request_id == "r"


def test_aggregator_full_flow() -> None:
    agg = _StreamAggregator(session_id="s", request_id="r")
    agg.feed(
        StreamEvent(
            type=StreamEventType.step,
            data={"name": "router", "status": "success", "duration_ms": 10},
        )
    )
    agg.feed(StreamEvent(type=StreamEventType.delta, data={"text": "hi"}))
    agg.feed(
        StreamEvent(
            type=StreamEventType.citation,
            data={"source": "doc_x", "score": 0.9, "snippet": "..."},
        )
    )
    agg.feed(
        StreamEvent(
            type=StreamEventType.tool_call, data={"name": "sql", "args": {"q": "..."}}
        )
    )
    agg.feed(
        StreamEvent(
            type=StreamEventType.tool_result,
            data={"name": "sql", "result": {"rows": 3}},
        )
    )
    agg.feed(
        StreamEvent(
            type=StreamEventType.metadata,
            data={
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                }
            },
        )
    )

    result = agg.result()
    assert result.answer == "hi"
    assert len(result.steps) == 1 and result.steps[0].name == "router"
    assert len(result.citations) == 1 and result.citations[0].source == "doc_x"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "sql"
    assert result.tool_calls[0].result == {"rows": 3}
    assert result.usage and result.usage.total_tokens == 15


def test_aggregator_done_overrides() -> None:
    """done event 的 data 直接作为 InvokeResult 字段（最终态）"""
    agg = _StreamAggregator(session_id="s", request_id="r")
    agg.feed(StreamEvent(type=StreamEventType.delta, data={"text": "partial"}))
    agg.feed(
        StreamEvent(
            type=StreamEventType.done,
            data={
                "answer": "complete answer",
                "steps": [{"name": "x", "status": "success"}],
                "citations": [],
                "tool_calls": [],
            },
        )
    )
    result = agg.result()
    # done 覆盖累积的 partial
    assert result.answer == "complete answer"
    assert len(result.steps) == 1


def test_invoke_result_validate_round_trip() -> None:
    r = InvokeResult(
        answer="hi",
        session_id="s",
        steps=[StepRecord(name="x")],
        citations=[Citation(source="doc")],
        tool_calls=[ToolCallRecord(name="t")],
        usage=Usage(total_tokens=100),
    )
    d = r.model_dump()
    r2 = InvokeResult.model_validate(d)
    assert r2.answer == r.answer
    assert r2.usage.total_tokens == 100
