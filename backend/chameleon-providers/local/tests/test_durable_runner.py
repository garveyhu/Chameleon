"""durable Slice2b/评审#2 —— run_agentkit 集成：

durable agent 无持久化 scope（end_user/session 均空）时 run_agentkit fail-closed 直接拒——
journal/HITL 落 AgentMemory 按 scope_ref 持久化，无 scope 则 memory no-op、journal 永久失效、
resume 后无限重暂停。故无 scope 必须显式报错而非静默跑成坏 journal（评审 #2）。

注：带真 scope 的完整 ask→paused→resolve→续跑 e2e 需真 DB（journal 持久化），属 Slice2c-endpoint；
agentkit 侧机制（含完整 pause→resume 循环）已由 test_durable_hitl.py 经 FakeTransport 覆盖。
"""

from __future__ import annotations

import sys
import types

import pytest

from chameleon.agentkit import AgentRun, ModelSlot, StreamEvent, StreamEventType, agent
from chameleon.providers.base.types import AgentDef, InvokeContext
from chameleon.providers.local.agentkit_runner import InProcessTransport, run_agentkit

_MOD = "chameleon._test_durable_runner.hitl"
_EMIT_MOD = "chameleon._test_durable_runner.emit"


def _register_durable_agent() -> None:
    if _MOD in sys.modules:
        return

    @agent(key="_t_hitl_runner", name="审批", models=[ModelSlot("chat", "c")], durable=True)
    async def handle(ctx: AgentRun):
        decision = await ctx.ask_human("批准这步吗？")
        yield f"决定：{decision}"

    mod = types.ModuleType(_MOD)
    mod.handle = handle  # type: ignore[attr-defined]
    handle.__module__ = _MOD
    sys.modules[_MOD] = mod


def _register_emit_agent() -> None:
    if _EMIT_MOD in sys.modules:
        return

    @agent(key="_t_hitl_emit", name="引用后审批", models=[ModelSlot("chat", "c")], durable=True)
    async def handle(ctx: AgentRun):
        ctx.emit(StreamEvent(type=StreamEventType.citation, data={"text": "ref"}))
        decision = await ctx.ask_human("批准这步吗？")  # call_index 0（citation emit 不计 index）
        yield f"决定：{decision}"

    mod = types.ModuleType(_EMIT_MOD)
    mod.handle = handle  # type: ignore[attr-defined]
    handle.__module__ = _EMIT_MOD
    sys.modules[_EMIT_MOD] = mod


def _mock_memory(monkeypatch) -> None:  # noqa: ANN001
    """把 InProcessTransport 的 DB memory 换成内存 dict（按 scope_ref+key），免 DB 测真 scope 路径。"""
    store: dict = {}

    async def _get(self, key, default=None):  # noqa: ANN001
        return store.get((self._scope_ref, key), default)

    async def _set(self, key, value):  # noqa: ANN001
        store[(self._scope_ref, key)] = value

    monkeypatch.setattr(InProcessTransport, "memory_get", _get)
    monkeypatch.setattr(InProcessTransport, "memory_set", _set)


@pytest.mark.asyncio
async def test_run_agentkit_durable_without_scope_fails_fast():
    """durable + 无 scope（session_id/end_user 均空）→ run_agentkit fail-closed 报错，不静默
    跑成 no-op journal（评审 #2：否则 resume 后无限重暂停）。"""
    _register_durable_agent()
    agent_def = AgentDef(
        key="_t_hitl_runner", provider="local",
        config={"__agentkit_module__": _MOD, "__agentkit_attr__": "handle"},
    )
    ctx = InvokeContext(
        agent_def=agent_def, input="hi", history=[], app_id="app1",
        session_id=None, request_id="req-hitl-1", stream=True,
    )
    with pytest.raises(RuntimeError, match="需持久化 scope"):
        _ = [ev async for ev in run_agentkit(ctx)]


@pytest.mark.asyncio
async def test_run_agentkit_pause_drain_and_resume_cycle(monkeypatch):
    """评审 #4/#5：真 scope（mock 内存）下完整 pause→resume——
    ① 暂停时 drain pause 前 emit 的 citation（不丢）+ emit pending step；
    ② resume（同 request_id + 答案经 context_vars→_seed_resume 回填）重放续跑完成。
    这是真 scope 路径（非 session_id=None 的 no-op 退化路径，评审指出后者是假验证）。"""
    _mock_memory(monkeypatch)
    _register_emit_agent()
    adef = AgentDef(
        key="_t_hitl_emit", provider="local",
        config={"__agentkit_module__": _EMIT_MOD, "__agentkit_attr__": "handle"},
    )

    def _ctx(cvars: dict | None = None) -> InvokeContext:
        return InvokeContext(
            agent_def=adef, input="hi", history=[], app_id="app1",
            session_id="s1", request_id="req-cycle", stream=True, context_vars=cvars or {},
        )

    # run 1：暂停。citation 在 ask_human 前 emit、AgentPaused 时经 drain 产出（评审 #5）
    ev1 = [e async for e in run_agentkit(_ctx())]
    assert any(e.type == StreamEventType.citation for e in ev1), "pause 前 citation 应被 drain"
    assert any(
        e.type == StreamEventType.step and e.data.get("name") == "human_input_pending" for e in ev1
    )
    assert not [e for e in ev1 if e.type == StreamEventType.delta]  # 暂停未产出答案

    # run 2：resume（同 request_id + 答案经 context_vars 回填 journal）→ 重放续跑完成
    ev2 = [e async for e in run_agentkit(_ctx({"_resume_answer": "同意", "_resume_call_index": 0}))]
    out = "".join(e.data.get("text", "") for e in ev2 if e.type == StreamEventType.delta)
    assert out == "决定：同意"


_CMPL_MOD = "chameleon._test_durable_runner.complete"


def _register_complete_agent() -> None:
    if _CMPL_MOD in sys.modules:
        return

    @agent(key="_t_hitl_cmpl", name="先complete再审批", models=[ModelSlot("chat", "c")], durable=True)
    async def handle(ctx: AgentRun):
        greeting = await ctx.complete(user="打招呼")        # call_index 0（journaled）
        decision = await ctx.ask_human("批准吗？")           # call_index 1（暂停点）
        yield f"{greeting}/{decision}"

    mod = types.ModuleType(_CMPL_MOD)
    mod.handle = handle  # type: ignore[attr-defined]
    handle.__module__ = _CMPL_MOD
    sys.modules[_CMPL_MOD] = mod


@pytest.mark.asyncio
async def test_run_agentkit_complete_replay_no_remodel_on_resume(monkeypatch):
    """评审 #6 覆盖空白：runner 路径下 complete 重放不重调模型（此前仅 FakeTransport 级覆盖）。
    durable handle 先 complete 再 ask_human；resume 时 complete@0 走 journal 返记录值、模型零再调。"""
    _mock_memory(monkeypatch)

    calls = {"n": 0}

    class _FakeMsg:
        def __init__(self, content: str) -> None:
            self.content = content
            self.tool_calls: list = []
            self.usage_metadata = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}

    class _FakeChat:
        def bind_tools(self, schemas):  # noqa: ANN001
            return self

        async def ainvoke(self, messages, **kw):  # noqa: ANN001
            calls["n"] += 1
            return _FakeMsg("你好")

    monkeypatch.setattr(InProcessTransport, "chat_model", lambda self, *, slot=None, model=None: _FakeChat())
    _register_complete_agent()
    adef = AgentDef(
        key="_t_hitl_cmpl", provider="local",
        config={"__agentkit_module__": _CMPL_MOD, "__agentkit_attr__": "handle"},
    )

    def _ctx(cvars: dict | None = None) -> InvokeContext:
        return InvokeContext(
            agent_def=adef, input="hi", history=[], app_id="app1",
            session_id="s1", request_id="req-cmpl", stream=True, context_vars=cvars or {},
        )

    # run 1：complete 真调模型 1 次 + journaled，ask_human 暂停
    _ = [e async for e in run_agentkit(_ctx())]
    assert calls["n"] == 1
    # run 2：resume → complete@0 走 journal（模型零再调）+ ask@1 返答案 → 续跑完成
    ev2 = [e async for e in run_agentkit(_ctx({"_resume_answer": "同意", "_resume_call_index": 1}))]
    out = "".join(e.data.get("text", "") for e in ev2 if e.type == StreamEventType.delta)
    assert out == "你好/同意"
    assert calls["n"] == 1, f"complete 重放应零再调模型，实际累计 {calls['n']} 次"


_RWT_MOD = "chameleon._test_durable_runner.rwt"
_rwt_exec = {"n": 0}


def _register_rwt_agent() -> None:
    if _RWT_MOD in sys.modules:
        return
    from chameleon.agentkit import tool

    @tool(name="_rwt_weather", description="查天气")
    async def _weather() -> dict:
        _rwt_exec["n"] += 1
        return {"temp": 20}

    @agent(key="_t_hitl_rwt", name="工具后审批", models=[ModelSlot("chat", "c")], durable=True)
    async def handle(ctx: AgentRun):
        # fine-grained：run_with_tools 逐步 journal 消耗多个 call_index——本例 1 轮工具 =
        # LLM step0(0) + 工具批(1) + LLM step1 收口(2)，故 ask_human 在 call_index 3。
        async for d in ctx.run_with_tools(user="查天气", tools=[_weather]):
            yield d
        decision = await ctx.ask_human("批准吗？")  # call_index 3（暂停点）
        yield f"/{decision}"

    mod = types.ModuleType(_RWT_MOD)
    mod.handle = handle  # type: ignore[attr-defined]
    handle.__module__ = _RWT_MOD
    sys.modules[_RWT_MOD] = mod


@pytest.mark.asyncio
async def test_run_agentkit_run_with_tools_replay_no_reexec_on_resume(monkeypatch):
    """T1-2 难片验收：durable agent 用 run_with_tools 跑通暂停-恢复，重放零重复计费/副作用。
    handle 先 run_with_tools（工具循环）再 ask_human；resume 时 run_with_tools@0 走 journal
    一次性吐、LLM 零再调、工具零再执行（粗粒度整轮 journal）。"""
    _mock_memory(monkeypatch)
    _rwt_exec["n"] = 0
    chat_state = {"n": 0}

    class _ToolThenFinal:
        def bind_tools(self, schemas):  # noqa: ANN001
            return self

        async def ainvoke(self, convo, **kw):  # noqa: ANN001
            chat_state["n"] += 1
            first = chat_state["n"] == 1

            class _M:
                tool_calls = (
                    [{"name": "_rwt_weather", "args": {}, "id": "c1"}] if first else []
                )
                content = "" if first else "最终答案"
                usage_metadata = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}

            return _M()

    monkeypatch.setattr(
        InProcessTransport, "chat_model", lambda self, *, slot=None, model=None: _ToolThenFinal()
    )
    _register_rwt_agent()
    adef = AgentDef(
        key="_t_hitl_rwt", provider="local",
        config={"__agentkit_module__": _RWT_MOD, "__agentkit_attr__": "handle"},
    )

    def _ctx(cvars: dict | None = None) -> InvokeContext:
        return InvokeContext(
            agent_def=adef, input="hi", history=[], app_id="app1",
            session_id="s1", request_id="req-rwt", stream=True, context_vars=cvars or {},
        )

    # run 1：run_with_tools 跑两轮 LLM + 执行工具一次 + journaled，ask_human 暂停
    ev1 = [e async for e in run_agentkit(_ctx())]
    assert any(
        e.type == StreamEventType.step and e.data.get("name") == "human_input_pending" for e in ev1
    )
    assert chat_state["n"] == 2 and _rwt_exec["n"] == 1

    # run 2：resume → run_with_tools 各步走 journal（LLM/工具零再调）+ ask@3 返答案 → 续跑完成
    ev2 = [e async for e in run_agentkit(_ctx({"_resume_answer": "同意", "_resume_call_index": 3}))]
    out = "".join(e.data.get("text", "") for e in ev2 if e.type == StreamEventType.delta)
    assert out == "最终答案/同意"
    assert chat_state["n"] == 2, f"run_with_tools 重放应零再调 LLM，实际 {chat_state['n']}"
    assert _rwt_exec["n"] == 1, f"run_with_tools 重放应零再执行工具，实际 {_rwt_exec['n']}"
