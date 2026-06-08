"""agentkit P0-1 工具调用单测：@tool schema 推断 + ReAct 循环（本地工具调度）。"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from chameleon.agentkit import AgentMetadata, AgentRun, BaseAgent, agent, tool
from chameleon.providers.base.types import StreamEventType
from chameleon.providers.local.agentkit_runner import InProcessTransport, _consume


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
async def test_class_style_handle_gets_ctx():
    """类式 @agent 定义 handle(self, run) → 注入 AgentRun（兑现两层共用 ctx）。"""

    @agent(key="_t_classic", name="经典类式", models=[])
    class _Classic(BaseAgent):
        @classmethod
        def get_metadata(cls):
            return AgentMetadata(id="_t_classic", name="经典类式", description="")

        async def handle(self, run: AgentRun):
            yield f"hi {run.query}"

    t = InProcessTransport(agent_key="_t_classic", bindings={}, slots={})
    run = AgentRun(
        transport=t, agent_key="_t_classic", query="bob",
        messages=[], history=[], session_id=None, config={},
    )
    inst = _Classic()
    texts = [
        e.data.get("text")
        async for e in _consume(inst.handle(run), t)
        if e.type == StreamEventType.delta
    ]
    assert "hi bob" in texts


def test_sandboxed_flag_and_policy():
    """@agent(sandboxed=True) → manifest.sandboxed；策略决策点不抛（接口预留）。"""
    from chameleon.providers.local.agentkit_runner import _resolve_sandbox_policy

    @agent(key="_t_sandboxed", name="S", models=[], sandboxed=True)
    async def _h(run):  # noqa: ANN001
        yield "x"

    man = _h.__agent_manifest__
    assert man.sandboxed is True
    _resolve_sandbox_policy("_t_sandboxed", man)  # 不抛即可（开发态进程内）


@pytest.mark.asyncio
async def test_call_agent_decrements_budget_cumulatively():
    """统一成本闸：扇出多次 call_agent 累计扣预算，每次拿到的是递减后的余额。"""
    from chameleon.providers.base import a2a_bridge

    seen_budgets: list[int] = []

    async def fake_caller(*, source, target, input, trace_id, budget_remaining, depth):  # noqa: ANN001
        seen_budgets.append(budget_remaining)
        return {"answer": "ok", "tokens": 60}

    a2a_bridge.set_a2a_caller(fake_caller)
    try:
        t = InProcessTransport(agent_key="x", bindings={}, slots={}, request_id="r1", budget=100)
        await t.call_agent("sub", input="a")
        await t.call_agent("sub", input="b")
        await t.call_agent("sub", input="c")
        # 第一次满额 100，之后递减：100 → 40 → 0（max(0, 40-60)）
        assert seen_budgets == [100, 40, 0]
    finally:
        a2a_bridge._CALLER = None


@pytest.mark.asyncio
async def test_run_tool_loop_truncates_on_budget_exhausted():
    """成本闸：agent token 预算耗尽 → 工具循环截断收口（不无限续轮）。"""

    @tool(name="calc", description="计算")
    async def calc(expression: str) -> dict:
        return {"value": 1}

    spec = calc.__tool_spec__
    t = InProcessTransport(agent_key="x", bindings={}, slots={}, budget=1)
    responses = [
        _FakeAI(tool_calls=[{"name": "calc", "args": {"expression": "1"}, "id": "c1"}]),
        _FakeAI(content="收口答案"),  # 截断后的最终 ainvoke
    ]
    t.chat_model = lambda *, slot=None, model=None: _FakeModel(responses)  # type: ignore[method-assign]
    out = [
        d
        async for d in t.run_tool_loop(
            messages=[("user", "算")], slot="chat", model=None,
            platform_keys=[], local_tools=[spec], max_steps=10,
        )
    ]
    assert "收口答案" in "".join(out)  # 预算 1 < 单轮 2 token → 一轮后截断
    steps = [e for e in t.drain() if e.type == StreamEventType.step]
    assert any("预算耗尽" in (e.data.get("output", {}).get("note", "")) for e in steps)


@pytest.mark.asyncio
async def test_run_tool_loop_dispatches_mcp_tool():
    """@agent(mcp_servers=) 加载的 MCP 工具（包成 ToolSpec 传 mcp_tools）自动进 ReAct 循环。"""
    from chameleon.agentkit import ToolSpec

    called: dict = {}

    async def mcp_handler(**args):  # noqa: ANN003
        called.update(args)
        return {"ok": True, "data": "MCP结果"}

    mcp_spec = ToolSpec(
        name="fs_read",
        description="读文件",
        parameters_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        handler=mcp_handler,
    )
    t = InProcessTransport(agent_key="x", bindings={}, slots={}, mcp_tools=[mcp_spec])
    responses = [
        _FakeAI(tool_calls=[{"name": "fs_read", "args": {"path": "/a"}, "id": "c1"}]),
        _FakeAI(content="答案含 MCP结果"),
    ]
    t.chat_model = lambda *, slot=None, model=None: _FakeModel(responses)  # type: ignore[method-assign]
    out = [
        d
        async for d in t.run_tool_loop(
            messages=[("user", "读")], slot="chat", model=None,
            platform_keys=[], local_tools=[], max_steps=4,
        )
    ]
    assert "MCP结果" in "".join(out)
    assert called == {"path": "/a"}  # MCP 工具经本地路径被调用


def test_class_agent_auto_synthesizes_metadata():
    """类式 @agent 未手写 get_metadata → 从 manifest 自动合成 + 可实例化（T3-5）。"""

    @agent(key="_t_synth", name="合成体", description="d", tags=["x"], models=[])
    class _C(BaseAgent):
        async def handle(self, run: AgentRun):  # noqa: ANN001
            yield "ok"

    inst = _C()  # 不应报「抽象类不可实例化」
    assert inst is not None
    md = _C.get_metadata()
    assert md.id == "_t_synth" and md.name == "合成体" and md.tags == ["x"]


@pytest.mark.asyncio
async def test_ctx_wrap_passthrough():
    """ctx.wrap(model) 逃生口：原样返回作者自带模型（T3-5）。"""
    t = InProcessTransport(agent_key="x", bindings={}, slots={})
    run = AgentRun(
        transport=t, agent_key="x", query="q",
        messages=[], history=[], session_id=None, config={},
    )
    sentinel = object()
    assert run.wrap(sentinel) is sentinel


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
