"""playground durable HITL（Slice 1）：_stream_agent 把 provider 的 human_input_pending step
透出为 {"pending"} chunk（前端渲染回填框）；resume 时经 resolve_resume 注入 context_vars +
原始 query 重放（评审17 #3：服务端权威读 call_index）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import chameleon.providers.base.registry as reg
from chameleon.providers.base.types import AgentDef, StreamEvent, StreamEventType
from chameleon.system.playground import service


def _wire_fake_provider(monkeypatch, stream_impl):
    agent = AgentDef(key="hitl", provider="p")
    monkeypatch.setattr(reg, "AGENTS", {"hitl": agent})
    monkeypatch.setattr(reg, "PROVIDERS", {"p": SimpleNamespace(stream=stream_impl)})


@pytest.mark.asyncio
async def test_stream_agent_surfaces_pending(monkeypatch):
    async def _stream(ctx):
        yield StreamEvent(
            type=StreamEventType.step,
            data={"name": "human_input_pending", "prompt": "批准删库?",
                  "call_index": 1, "run_id": "run-1"},
        )

    _wire_fake_provider(monkeypatch, _stream)
    chunks = [
        c
        async for c in service._stream_agent(
            invoke_agent_key="hitl",
            messages=[{"role": "user", "content": "删库"}],
            session_id="s1", request_id="run-1", app_id="app",
        )
    ]
    pend = [c["pending"] for c in chunks if "pending" in c]
    assert pend and pend[0]["prompt"] == "批准删库?" and pend[0]["run_id"] == "run-1"
    assert pend[0]["call_index"] == 1


@pytest.mark.asyncio
async def test_stream_agent_resume_injects_context_and_query(monkeypatch):
    """resume：经 resolve_resume 读 call_index + 原始 query → 注入 ctx.context_vars + 用原始 query。"""
    seen = {}

    async def _stream(ctx):
        seen["cvars"] = dict(ctx.context_vars or {})
        seen["input"] = ctx.input
        seen["session_id"] = ctx.session_id
        seen["request_id"] = ctx.request_id
        yield StreamEvent(type=StreamEventType.delta, data={"text": "续跑完成"})

    _wire_fake_provider(monkeypatch, _stream)
    monkeypatch.setattr(
        "chameleon.engine.agent.durable.resolve_resume",
        lambda key, scope: _fake_spec(),
    )

    chunks = [
        c
        async for c in service._stream_agent(
            invoke_agent_key="hitl",
            messages=[{"role": "user", "content": "拒绝"}],  # resume 时的人工答案
            session_id="s1", request_id="r-new", app_id="app",
            resume_run_id="run-1", resume_answer="拒绝",
        )
    ]
    assert any(c.get("delta") == "续跑完成" for c in chunks)
    assert seen["cvars"]["_resume_call_index"] == 1
    assert seen["cvars"]["_resume_answer"] == "拒绝"
    assert seen["input"] == "删除生产库"  # 原始 query 重放，非人工答案
    assert seen["session_id"] == "s1"  # 会话 session 即 durable scope，首跑/resume 一致，不变
    assert seen["request_id"] == "run-1"  # = spec.run_id，命中 journal 重放


async def _fake_spec():
    from chameleon.engine.agent.durable import ResumeSpec

    return ResumeSpec(call_index=1, query="删除生产库", run_id="run-1")
