"""durable Slice2b —— run_agentkit 集成：@agent(durable=True) 的 ctx.ask_human 暂停时，
run_agentkit 捕获 AgentPaused 并 emit human_input_pending step 事件（不当失败 error 上抛）。

不依赖 DB：session_id=None → journal no-op，但 ask_human 仍抛 AgentPaused → run_agentkit 捕获，
正好验证 Slice2b 新增的捕获→step 信号路径（journal 重放/resume 续跑的 DB 路径属真 e2e/Slice2c）。
"""

from __future__ import annotations

import sys
import types

import pytest

from chameleon.agentkit import AgentRun, ModelSlot, agent
from chameleon.providers.base.types import AgentDef, InvokeContext, StreamEventType
from chameleon.providers.local.agentkit_runner import run_agentkit

_MOD = "chameleon._test_durable_runner.hitl"


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


@pytest.mark.asyncio
async def test_run_agentkit_emits_pending_on_ask_human():
    _register_durable_agent()
    agent_def = AgentDef(
        key="_t_hitl_runner", provider="local",
        config={"__agentkit_module__": _MOD, "__agentkit_attr__": "handle"},
    )
    ctx = InvokeContext(
        agent_def=agent_def, input="hi", history=[], app_id="app1",
        session_id=None, request_id="req-hitl-1", stream=True,
    )
    events = [ev async for ev in run_agentkit(ctx)]

    pending = [
        e for e in events
        if e.type == StreamEventType.step and e.data.get("name") == "human_input_pending"
    ]
    assert pending, f"应 emit human_input_pending step，实际：{[e.type for e in events]}"
    assert pending[0].data["status"] == "paused"
    assert pending[0].data["prompt"] == "批准这步吗？"
    assert pending[0].data["run_id"] == "req-hitl-1"
    # 暂停不算失败：无 error 事件、handle 未产出正常答案
    assert not [e for e in events if e.type == StreamEventType.error]
    assert not [e for e in events if e.type == StreamEventType.delta]
