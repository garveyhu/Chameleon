"""agentkit P0-1 工具调用单测：@tool schema 推断 + ReAct 循环（本地工具调度）。"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from chameleon.agentkit import AgentRun, tool
from chameleon.providers.base.types import StreamEventType
from chameleon.providers.local.agentkit_runner import InProcessTransport


def test_tool_schema_inference():
    @tool(name="get_weather", description="查天气")
    async def get_weather(city: str, days: int = 1) -> dict:
        return {"city": city}

    spec = get_weather.__tool_spec__
    assert spec.name == "get_weather"
    schema = spec.parameters_schema
    assert schema["properties"]["city"]["type"] == "string"
    assert schema["properties"]["days"]["type"] == "integer"
    assert schema["required"] == ["city"]  # 有默认值的 days 非必填


class _FakeAI:
    def __init__(self, content: str = "", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.usage_metadata = {
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
        }


class _FakeModel:
    def __init__(self, responses):
        self._responses = list(responses)

    def bind_tools(self, schemas):  # noqa: ANN001
        return self

    async def ainvoke(self, messages):  # noqa: ANN001
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_run_tool_loop_dispatches_local_tool():
    @tool(name="calc", description="计算")
    async def calc(expression: str) -> dict:
        return {"value": 42}

    spec = calc.__tool_spec__
    t = InProcessTransport(agent_key="x", bindings={}, slots={}, tool_keys=[])
    responses = [
        _FakeAI(tool_calls=[{"name": "calc", "args": {"expression": "40+2"}, "id": "c1"}]),
        _FakeAI(content="答案是 42"),
    ]
    t.chat_model = lambda *, slot=None, model=None: _FakeModel(responses)  # type: ignore[method-assign]

    out: list[str] = []
    async for d in t.run_tool_loop(
        messages=[("user", "算 40+2")],
        slot="chat",
        model=None,
        platform_keys=[],
        local_tools=[spec],
        max_steps=4,
    ):
        out.append(d)

    assert "答案是 42" in "".join(out)
    types = [e.type for e in t.drain()]
    assert StreamEventType.tool_call in types
    assert StreamEventType.tool_result in types


class _FakeStructured:
    def __init__(self, inst):
        self._inst = inst

    async def ainvoke(self, messages, **kw):  # noqa: ANN001
        return self._inst


class _FakeChatStructured:
    def __init__(self, inst):
        self._inst = inst

    def with_structured_output(self, schema):  # noqa: ANN001
        return _FakeStructured(self._inst)


@pytest.mark.asyncio
async def test_complete_with_schema_returns_instance():
    class Triage(BaseModel):
        category: str
        confidence: float

    inst = Triage(category="技术", confidence=0.9)
    t = InProcessTransport(agent_key="x", bindings={}, slots={})
    t.chat_model = lambda *, slot=None, model=None: _FakeChatStructured(inst)  # type: ignore[method-assign]
    run = AgentRun(
        transport=t,
        agent_key="x",
        query="q",
        messages=[],
        history=[],
        session_id=None,
        config={},
    )
    res = await run.complete(user="把这句分类", schema=Triage)
    assert isinstance(res, Triage)
    assert res.category == "技术" and res.confidence == 0.9


@pytest.mark.asyncio
async def test_call_agent_delegates_to_bridge():
    from chameleon.providers.base import a2a_bridge

    captured: dict = {}

    async def fake_caller(*, source, target, input, trace_id, budget_remaining, depth):  # noqa: ANN001
        captured.update(
            source=source, target=target, input=input,
            trace_id=trace_id, budget=budget_remaining, depth=depth,
        )
        return {"answer": "子答案", "tokens": 5}

    a2a_bridge.set_a2a_caller(fake_caller)
    try:
        t = InProcessTransport(
            agent_key="orch", bindings={}, slots={},
            request_id="trace-1", a2a_depth=1, budget=9000,
        )
        ans = await t.call_agent("critic", input="草稿")
        assert ans == "子答案"
        assert captured["source"] == "orch" and captured["target"] == "critic"
        assert captured["depth"] == 2  # 自动 +1
        assert captured["trace_id"] == "trace-1" and captured["budget"] == 9000
    finally:
        a2a_bridge._CALLER = None  # 清理，避免污染其它测试


@pytest.mark.asyncio
async def test_run_tool_loop_no_tool_calls_returns_text():
    t = InProcessTransport(agent_key="x", bindings={}, slots={}, tool_keys=[])
    t.chat_model = lambda *, slot=None, model=None: _FakeModel(  # type: ignore[method-assign]
        [_FakeAI(content="直接回答")]
    )
    out = [
        d
        async for d in t.run_tool_loop(
            messages=[("user", "hi")],
            slot="chat",
            model=None,
            platform_keys=[],
            local_tools=[],
            max_steps=4,
        )
    ]
    assert "".join(out) == "直接回答"
