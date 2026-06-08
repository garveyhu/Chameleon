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

from chameleon.agentkit import AgentRun, ModelSlot, agent
from chameleon.providers.base.types import AgentDef, InvokeContext
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
