"""durable 覆盖「中」片真库往返（T1-2）：call_agent / gather / stream / route。

每类：首跑经 transport 真调 1 次 + journal 落 AgentMemory（真 test-DB）；重放（同 run_id、
fresh AgentRun）按 call_index 返记录值、**transport 零再调**。子 agent 扇出 / 流式 / 复合路由
重放零重复计费/副作用——durable 跑真 agentic 活的核心契约。

不 mock DB（journal 走真 AgentMemory）；被 journal 的外部调用用计数 fake 注入。
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete

from chameleon.agentkit import AgentRun
from chameleon.agentkit._runtime import _RouteChoice
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import AgentMemory
from chameleon.providers.local.agentkit_runner import InProcessTransport

_AGENT = "_t_durable_mid"


async def _clean() -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(delete(AgentMemory).where(AgentMemory.agent_key == _AGENT))
        await s.commit()


def _durable_run(run_id: str) -> AgentRun:
    t = InProcessTransport(agent_key=_AGENT, bindings={}, slots={}, scope_ref="user-A")
    return AgentRun(
        transport=t, agent_key=_AGENT, query="q", messages=[], history=[],
        session_id="user-A", config={}, durable=True, run_id=run_id,
    )


@pytest.mark.asyncio
async def test_call_agent_journaled_and_replayed(monkeypatch) -> None:
    await _clean()
    calls = {"n": 0}

    async def fake_call_agent(self, target, *, input):  # noqa: ANN001, ANN202
        calls["n"] += 1
        return f"{target}:{input}"

    monkeypatch.setattr(InProcessTransport, "call_agent", fake_call_agent)
    rid = "rid-ca-1"
    a1 = await _durable_run(rid).call_agent("bot", input="hi")
    assert calls["n"] == 1 and a1 == "bot:hi"
    a2 = await _durable_run(rid).call_agent("bot", input="hi")
    assert calls["n"] == 1, "重放不应重跑子 agent"
    assert a2 == "bot:hi"
    await _clean()


@pytest.mark.asyncio
async def test_gather_journaled_and_replayed(monkeypatch) -> None:
    await _clean()
    calls = {"n": 0}

    async def fake_gather(self, calls_, *, timeout=None):  # noqa: ANN001, ANN202
        calls["n"] += 1
        return [f"{t}:{i}" for t, i in calls_]

    monkeypatch.setattr(InProcessTransport, "gather", fake_gather)
    rid = "rid-ga-1"
    items = [("a", "1"), ("b", "2")]
    r1 = await _durable_run(rid).gather(items)
    assert calls["n"] == 1 and r1 == ["a:1", "b:2"]
    r2 = await _durable_run(rid).gather(items)
    assert calls["n"] == 1, "重放不应重跑扇出"
    assert r2 == ["a:1", "b:2"]
    await _clean()


class _FakeStreamChat:
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.astream_calls = 0

    async def astream(self, messages, **kw):  # noqa: ANN001
        self.astream_calls += 1
        for i, c in enumerate(self.chunks):
            last = i == len(self.chunks) - 1

            class _Chunk:
                content = c
                usage_metadata = (
                    {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}
                    if last else {}
                )

            yield _Chunk()


@pytest.mark.asyncio
async def test_stream_journaled_and_replayed(monkeypatch) -> None:
    await _clean()
    chat = _FakeStreamChat(["你好", "，", "世界"])
    monkeypatch.setattr(
        InProcessTransport, "chat_model",
        lambda self, *, slot=None, model=None: chat,
    )
    rid = "rid-st-1"
    out1 = "".join([c async for c in _durable_run(rid).stream(user="q")])
    assert chat.astream_calls == 1 and out1 == "你好，世界"
    # 重放：一次性吐累积文本，不重调 astream
    out2 = "".join([c async for c in _durable_run(rid).stream(user="q")])
    assert chat.astream_calls == 1, "重放不应重流"
    assert out2 == "你好，世界"
    await _clean()


@pytest.mark.asyncio
async def test_route_composes_journaled_primitives(monkeypatch) -> None:
    """route 由 complete(schema)+call_agent 拼成，两者均 journal → 重放零重调（复合透明）。"""
    await _clean()
    struct_calls = {"n": 0}
    ca_calls = {"n": 0}

    class _FakeStructured:
        async def ainvoke(self, messages, **kw):  # noqa: ANN001
            struct_calls["n"] += 1
            return _RouteChoice(agent_key="sql-bot", reason="查库")

    monkeypatch.setattr(
        InProcessTransport, "structured_model",
        lambda self, *, slot=None, model=None, schema=None: _FakeStructured(),
    )

    async def fake_call_agent(self, target, *, input):  # noqa: ANN001, ANN202
        ca_calls["n"] += 1
        return f"answered-by-{target}"

    monkeypatch.setattr(InProcessTransport, "call_agent", fake_call_agent)

    agents = [("sql-bot", "查数据库"), ("doc-bot", "查文档")]
    rid = "rid-rt-1"
    a1 = await _durable_run(rid).route("查订单", agents)
    assert a1 == "answered-by-sql-bot"
    assert struct_calls["n"] == 1 and ca_calls["n"] == 1

    # 重放：route 体重跑，但内层 complete(schema)@idx0 + call_agent@idx1 均 journal-hit，零重调
    a2 = await _durable_run(rid).route("查订单", agents)
    assert a2 == "answered-by-sql-bot"
    assert struct_calls["n"] == 1, "重放不应重调路由 LLM"
    assert ca_calls["n"] == 1, "重放不应重跑被路由的子 agent"
    await _clean()
