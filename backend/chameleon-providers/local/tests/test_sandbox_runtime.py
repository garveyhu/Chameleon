"""沙箱生产 parent run_sandboxed e2e（T4-2 Phase 2 Slice 1b-2）：fake broker + 真子进程。"""

from __future__ import annotations

import sys
import textwrap

import pytest

from chameleon.providers.base.types import StreamEventType
from chameleon.providers.local.sandbox import run_sandboxed

_AGENT = textwrap.dedent(
    '''
    from chameleon.agentkit import agent, AgentRun, ModelSlot

    @agent(key="_sbx_rt", name="t", models=[ModelSlot("chat", "c")])
    async def handle(ctx: AgentRun):
        ans = await ctx.complete(system="s", user=ctx.query)
        yield "答:" + ans
    '''
)


class _FakeMsg:
    def __init__(self, content):
        self.content = content


class _FakeModel:
    async def ainvoke(self, messages, **_kw):
        # 校验 user 消息过线
        assert any(m[1] == "杭州" for m in messages if isinstance(m, tuple))
        return _FakeMsg("BROKER_RESOLVED")

    async def astream(self, messages, **_kw):
        for piece in ("流", "式", "块"):
            yield _FakeMsg(piece)


class _FakeBroker:
    def chat_model(self, *, slot=None, model=None):
        return _FakeModel()


_STREAM_AGENT = textwrap.dedent(
    '''
    from chameleon.agentkit import agent, AgentRun, ModelSlot

    @agent(key="_sbx_stream", name="t", models=[ModelSlot("chat", "c")])
    async def handle(ctx: AgentRun):
        async for d in ctx.stream(system="s", user=ctx.query):
            yield d
    '''
)


@pytest.mark.asyncio
async def test_run_sandboxed_parent_loop_and_broker(tmp_path):
    (tmp_path / "sbx_rt_mod.py").write_text(_AGENT, encoding="utf-8")
    events = []
    async for ev in run_sandboxed(
        module="sbx_rt_mod",
        attr="handle",
        query="杭州",
        broker=_FakeBroker(),
        env_extra={"PYTHONPATH": __import__("os").pathsep.join([str(tmp_path), *sys.path])},
    ):
        events.append(ev)
    deltas = [e.data.get("text", "") for e in events if e.type == StreamEventType.delta]
    assert "".join(deltas) == "答:BROKER_RESOLVED"  # 子进程 ctx.complete 经 broker 解析回流
    assert not any(e.type == StreamEventType.error for e in events)


@pytest.mark.asyncio
async def test_broker_run_tool_scope_rejects_undeclared():
    """broker scope 红线：子进程调未声明的平台工具 → 拒绝（不执行）。"""
    from chameleon.providers.local.sandbox.runtime import _resolve_rpc

    class _Broker:
        _tool_keys = ["http"]  # 只声明了 http

    # 调声明外的工具 → 越权拒
    res = await _resolve_rpc(_Broker(), {"method": "run_tool", "args": {"name": "sql", "args": {}}})
    assert res["ok"] is False and "越权" in res["error"]


@pytest.mark.asyncio
async def test_run_sandboxed_streaming(tmp_path):
    (tmp_path / "sbx_stream_mod.py").write_text(_STREAM_AGENT, encoding="utf-8")
    deltas = []
    async for ev in run_sandboxed(
        module="sbx_stream_mod", attr="handle", query="杭州", broker=_FakeBroker(),
        env_extra={"PYTHONPATH": __import__("os").pathsep.join([str(tmp_path), *sys.path])},
    ):
        if ev.type == StreamEventType.delta:
            deltas.append(ev.data.get("text", ""))
    # 子进程 ctx.stream → chat_stream rpc → broker.astream 多块经 stream_chunk 帧回流
    assert "".join(deltas) == "流式块"
