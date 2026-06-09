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


@pytest.mark.asyncio
async def test_tool_loop_budget_gate_truncates_real():
    """成本闸真触发（评审12）：预算耗尽时工具循环第 1 轮后截断收口，非跑满 max_steps、非超支。

    模型“总想调工具”（每轮都返 tool_calls），唯一能停它的是预算闸——故能区分“预算耗尽截断”
    vs“达 max_steps 上限”。budget=1，_FakeAI 每轮 total_tokens=2 → 第 1 轮 charge 后 budget→0。
    """
    @tool(name="calc", description="计算")
    async def calc(expression: str) -> dict:
        return {"value": 1}

    spec = calc.__tool_spec__
    t = InProcessTransport(agent_key="x", bindings={}, slots={}, tool_keys=[], budget=1)
    # 全部是 tool_calls 响应（>max_steps+收口）：闸坏会跑满 10 轮“达上限”，闸好第 1 轮后“预算耗尽”
    responses = [
        _FakeAI(tool_calls=[{"name": "calc", "args": {"expression": "1"}, "id": f"c{i}"}])
        for i in range(12)
    ]
    t.chat_model = lambda *, slot=None, model=None: _FakeModel(responses)  # type: ignore[method-assign]

    async for _ in t.run_tool_loop(
        messages=[("user", "算")], slot="chat", model=None,
        platform_keys=[], local_tools=[spec], max_steps=10,
    ):
        pass

    events = t.drain()
    notes = [e.data.get("output", {}).get("note", "")
             for e in events if e.type == StreamEventType.step]
    assert any("预算耗尽" in n for n in notes), f"预算闸应触发截断，实际 notes={notes}"
    # 第 1 轮后即截断：仅 1 轮 tool_call（非跑满 max_steps=10），证是预算闸而非上限
    n_tool_rounds = sum(1 for e in events if e.type == StreamEventType.tool_call)
    assert n_tool_rounds == 1, f"预算闸应在第 1 轮后截断，实际跑了 {n_tool_rounds} 轮"


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


def test_sandboxed_flag_and_policy(monkeypatch):
    """@agent(sandboxed=True) → manifest.sandboxed；dev 默认不走沙箱（进程内便利）。"""
    from chameleon.providers.local.agentkit_runner import _should_sandbox

    @agent(key="_t_sandboxed", name="S", models=[], sandboxed=True)
    async def _h(run):  # noqa: ANN001
        yield "x"

    man = _h.__agent_manifest__
    assert man.sandboxed is True
    monkeypatch.delenv("CHAMELEON_SANDBOX_FORCE", raising=False)
    monkeypatch.setenv("CHAMELEON_ENV", "dev")
    assert _should_sandbox(man) is False  # dev 进程内


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


def test_should_sandbox_routing(monkeypatch):
    """沙箱路由决策（T4-2 Slice 4）：生产+sandboxed→走真沙箱；dev 默认进程内；force/豁免覆盖。"""
    from chameleon.providers.local.agentkit_runner import _should_sandbox

    class _M:
        sandboxed = True

    monkeypatch.delenv("CHAMELEON_SANDBOX_FORCE", raising=False)
    monkeypatch.delenv("CHAMELEON_SANDBOX_ALLOW_INPROCESS", raising=False)

    # 非沙箱：永不走沙箱
    monkeypatch.setenv("CHAMELEON_ENV", "production")
    assert _should_sandbox(type("N", (), {"sandboxed": False})()) is False
    # 非生产：默认进程内（便利）
    monkeypatch.setenv("CHAMELEON_ENV", "dev")
    assert _should_sandbox(_M()) is False
    # 生产 + sandboxed + 无豁免 → 走真沙箱
    monkeypatch.setenv("CHAMELEON_ENV", "production")
    assert _should_sandbox(_M()) is True
    # 生产 + 显式信任豁免 → 进程内
    monkeypatch.setenv("CHAMELEON_SANDBOX_ALLOW_INPROCESS", "1")
    assert _should_sandbox(_M()) is False
    # FORCE：dev 也强制走沙箱（本地验隔离）
    monkeypatch.setenv("CHAMELEON_ENV", "dev")
    monkeypatch.setenv("CHAMELEON_SANDBOX_FORCE", "1")
    assert _should_sandbox(_M()) is True


@pytest.mark.asyncio
async def test_gather_budget_split_and_order(monkeypatch):
    """ctx.gather 并行扇出：预算按分支数均分（防超支）+ 保序 + 事后扣实际总额。"""
    import chameleon.providers.base.a2a_bridge as bridge

    seen_budgets: list[int] = []

    async def _fake_caller(*, source, target, input, trace_id, budget_remaining, depth):
        seen_budgets.append(budget_remaining)
        return {"answer": f"ans-{target}", "tokens": 100}

    monkeypatch.setattr(bridge, "get_a2a_caller", lambda: _fake_caller)

    t = InProcessTransport(
        agent_key="x", bindings={}, slots={}, request_id="req-1", budget=900
    )
    answers = await t.gather([("a", "q1"), ("b", "q2"), ("c", "q3")])
    # 保序
    assert answers == ["ans-a", "ans-b", "ans-c"]
    # 预算均分：900 // 3 = 300 给每个并行分支（防各拿全额 900 超支）
    assert seen_budgets == [300, 300, 300]
    # 事后按实际总消耗扣减：900 - 3×100 = 600
    assert t._budget == 600


@pytest.mark.asyncio
async def test_gather_empty():
    t = InProcessTransport(agent_key="x", bindings={}, slots={})
    assert await t.gather([]) == []


@pytest.mark.asyncio
async def test_gather_charges_successful_on_partial_failure(monkeypatch):
    """评审7 🔴：一支失败时，成功兄弟分支已花的钱仍结清（成本闸不泄漏），再重抛异常。"""
    import chameleon.providers.base.a2a_bridge as bridge

    async def _caller(*, source, target, input, trace_id, budget_remaining, depth):
        if target == "bad":
            raise RuntimeError("boom")
        return {"answer": f"ok-{target}", "tokens": 50}

    monkeypatch.setattr(bridge, "get_a2a_caller", lambda: _caller)
    t = InProcessTransport(
        agent_key="x", bindings={}, slots={}, request_id="r", budget=900
    )
    with pytest.raises(RuntimeError, match="boom"):
        await t.gather([("good", "q1"), ("bad", "q2")])
    # 成功分支 good（50 token）已结清：900-50=850，不因 bad 失败被洗白
    assert t._budget == 850


@pytest.mark.asyncio
async def test_route_supervisor_picks_and_delegates():
    """ctx.route：LLM 据描述选最合适子智能体并委托（supervisor 编排模式）。"""
    import types

    from chameleon.agentkit._runtime import AgentRun
    from chameleon.agentkit.testing import FakeTransport

    t = FakeTransport(
        structured=types.SimpleNamespace(agent_key="doc-bot", reason="文档类"),
        call_agent_reply="DOC_ANSWER",
    )
    run = AgentRun(
        transport=t, agent_key="sup", query="查手册", messages=[], history=[],
        session_id=None, config={},
    )
    ans = await run.route("查手册", [("sql-bot", "查数据库"), ("doc-bot", "查文档")])
    assert ans == "DOC_ANSWER"
    assert ("call_agent", ("doc-bot", "查手册")) in t.invocations  # 路由到 doc-bot


@pytest.mark.asyncio
async def test_handoff_packs_conversation_context():
    """ctx.handoff：把完整对话上下文（history + query）打包移交目标接手。"""
    import types

    from chameleon.agentkit._runtime import AgentRun
    from chameleon.agentkit.testing import FakeTransport

    hist = [
        types.SimpleNamespace(role="user", text=lambda: "我想退货"),
        types.SimpleNamespace(role="assistant", text=lambda: "请提供订单号"),
    ]
    t = FakeTransport(call_agent_reply="EXPERT_ANSWER")
    run = AgentRun(
        transport=t, agent_key="triage", query="订单 12345", messages=[],
        history=hist, session_id=None, config={},
    )
    ans = await run.handoff("refund-bot", instruction="处理退货")
    assert ans == "EXPERT_ANSWER"
    _kind, (target, inp) = t.invocations[-1]
    assert target == "refund-bot"
    # 完整上下文 + 接手指示都在 input 里（call_agent 只传一条 input，故打包）
    assert "处理退货" in inp and "我想退货" in inp and "订单 12345" in inp


@pytest.mark.asyncio
async def test_route_single_candidate_direct():
    """单候选 → 直接委托，不走 LLM 路由。"""
    from chameleon.agentkit._runtime import AgentRun
    from chameleon.agentkit.testing import FakeTransport

    t = FakeTransport(call_agent_reply="ONLY")
    run = AgentRun(
        transport=t, agent_key="sup", query="q", messages=[], history=[],
        session_id=None, config={},
    )
    assert await run.route("q", [("only-bot", "啥都行")]) == "ONLY"
    # 未触发结构化路由（complete schema），直接 call_agent
    assert [i[0] for i in t.invocations] == ["call_agent"]


@pytest.mark.asyncio
async def test_route_structured_failure_falls_back():
    """评审8 🟠：结构化路由失败（模型不支持/返 None）→ 回退首个候选，route 不整体炸。"""
    from chameleon.agentkit._runtime import AgentRun
    from chameleon.agentkit.testing import FakeTransport

    t = FakeTransport(call_agent_reply="FB")  # structured 默认 None → choice.agent_key 抛 → 兜底
    run = AgentRun(
        transport=t, agent_key="s", query="q", messages=[], history=[],
        session_id=None, config={},
    )
    ans = await run.route("q", [("a", "x"), ("b", "y")])
    assert ans == "FB"
    assert ("call_agent", ("a", "q")) in t.invocations  # 回退首个候选 a


@pytest.mark.asyncio
async def test_gather_timeout_per_branch(monkeypatch):
    """评审8 🟠：gather timeout 让 hang 的分支超时失败，不永等；成功分支仍结清。"""
    import asyncio
    import time

    import chameleon.providers.base.a2a_bridge as bridge

    async def _caller(*, source, target, input, trace_id, budget_remaining, depth):
        if target == "slow":
            await asyncio.sleep(10)
        return {"answer": f"ok-{target}", "tokens": 30}

    monkeypatch.setattr(bridge, "get_a2a_caller", lambda: _caller)
    t = InProcessTransport(
        agent_key="x", bindings={}, slots={}, request_id="r", budget=600
    )
    start = time.monotonic()
    with pytest.raises((TimeoutError, asyncio.TimeoutError)):
        await t.gather([("fast", "q1"), ("slow", "q2")], timeout=0.15)
    assert time.monotonic() - start < 3  # 不等满 10s
    assert t._budget == 570  # fast(30) 已结清，slow 超时不影响 fast 计账


@pytest.mark.asyncio
async def test_route_empty_raises():
    from chameleon.agentkit._runtime import AgentRun
    from chameleon.agentkit.testing import FakeTransport

    run = AgentRun(
        transport=FakeTransport(), agent_key="s", query="q", messages=[], history=[],
        session_id=None, config={},
    )
    with pytest.raises(ValueError, match="至少需要一个候选"):
        await run.route("q", [])


@pytest.mark.asyncio
async def test_gather_default_path_via_agentrun():
    """公共面 ctx.gather 委托 transport，默认实现（非 InProcess）= 并发 call_agent 保序。"""
    from chameleon.agentkit._runtime import AgentRun, RuntimeTransport

    class _T(RuntimeTransport):  # 只实现 call_agent，gather 走 ABC 默认实现
        async def call_agent(self, target, *, input):
            return f"{target}:{input}"

        def chat_model(self, **k): ...
        def structured_model(self, **k): ...
        async def kb_search(self, *a, **k): ...
        async def run_tool_loop(self, **k): ...
        async def memory_get(self, *a, **k): ...
        async def memory_set(self, *a, **k): ...
        async def memory_all(self): ...
        async def memory_search(self, *a, **k): ...
        async def media_generate(self, **k): ...
        def span(self, name, *, type="span"): ...
        def emit(self, event): ...
        def track_usage(self, usage): ...

    run = AgentRun(
        transport=_T(), agent_key="x", query="q", messages=[], history=[],
        session_id=None, config={},
    )
    out = await run.gather([("a", "1"), ("b", "2")])
    assert out == ["a:1", "b:2"]  # 保序


def test_untrusted_fail_closed_requires_docker(monkeypatch):
    """评审6：untrusted 信任级生产必须 docker 真隔离，无 docker runtime 则拒绝运行（fail-closed）。"""
    import pytest

    from chameleon.providers.local.agentkit_runner import _assert_isolation_for_tier

    class _Untrusted:
        trust_tier = "untrusted"

    class _Internal:
        trust_tier = "internal"

    monkeypatch.setenv("CHAMELEON_ENV", "production")
    # untrusted + 生产 + 非 docker runtime → 拒绝（不静默退化到漏隔离子进程）
    monkeypatch.setenv("CHAMELEON_SANDBOX_RUNTIME", "subprocess")
    with pytest.raises(RuntimeError, match="docker 真隔离"):
        _assert_isolation_for_tier(_Untrusted(), "u")
    # untrusted + docker runtime → 放行
    monkeypatch.setenv("CHAMELEON_SANDBOX_RUNTIME", "docker")
    _assert_isolation_for_tier(_Untrusted(), "u")  # 不抛
    # internal 信任级：子进程档即可，不强制 docker
    monkeypatch.setenv("CHAMELEON_SANDBOX_RUNTIME", "subprocess")
    _assert_isolation_for_tier(_Internal(), "i")  # 不抛
    # untrusted 但非生产：dev 便利，不强制（_should_sandbox 已挡 dev 进沙箱）
    monkeypatch.setenv("CHAMELEON_ENV", "dev")
    _assert_isolation_for_tier(_Untrusted(), "u")  # 不抛


def test_track_usage_accumulates():
    """transport.track_usage 累计 → usage_total 求和（A2A 上报基础，评审2 #25）。"""
    t = InProcessTransport(agent_key="x", bindings={}, slots={})
    t.track_usage({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
    t.track_usage({"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5})
    t.track_usage(None)  # None 安全
    assert t.usage_total() == {
        "prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20,
    }


@pytest.mark.asyncio
async def test_run_tool_loop_accumulates_usage_for_reporting():
    """工具循环每轮模型 usage 计入 transport，供 run_agentkit 流末上报 → A2A 计账非 no-op。"""
    t = InProcessTransport(agent_key="x", bindings={}, slots={})
    t.chat_model = lambda *, slot=None, model=None: _FakeModel([_FakeAI(content="答案")])  # type: ignore[method-assign]
    _ = [
        d
        async for d in t.run_tool_loop(
            messages=[("user", "q")], slot="chat", model=None,
            platform_keys=[], local_tools=[], max_steps=4,
        )
    ]
    # _FakeAI usage_metadata total=2 → 累计进 usage_total
    assert t.usage_total()["total_tokens"] >= 2


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
