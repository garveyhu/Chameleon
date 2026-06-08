"""agentkit 作者测试套件自测（dogfood FakeTransport / make_run / collect）。"""

from __future__ import annotations

import pytest

from chameleon.agentkit import AgentRun, Doc, ModelSlot, agent, tool
from chameleon.agentkit.testing import FakeTransport, collect, make_run


@agent(key="_kit_rag", name="kit-rag", models=[ModelSlot("chat", "对话模型")], kb=True)
async def _rag(ctx: AgentRun):
    docs = await ctx.kb.search(ctx.query)
    async for d in ctx.stream(slot="chat", system="s", user=ctx.query, context=docs):
        yield d


@pytest.mark.asyncio
async def test_kit_kb_and_reply():
    t = FakeTransport(replies=["北京今天晴"], kb=[Doc(text="北京 天气晴")])
    run = make_run(_rag, query="北京天气", transport=t)
    out = await collect(_rag(run))
    assert "晴" in out
    # 模型被调用过（stream）
    assert any(k == "astream" for k, _ in t.invocations)


@tool(name="kitcalc", description="算")
async def _calc(x: int) -> dict:
    return {"v": x * 2}


@agent(key="_kit_tool", name="kit-tool", models=[ModelSlot("chat", "对话模型")])
async def _toolagent(ctx: AgentRun):
    async for d in ctx.run_with_tools(slot="chat", user=ctx.query, tools=[_calc]):
        yield d


@pytest.mark.asyncio
async def test_kit_tool_dispatch():
    t = FakeTransport(replies=["结果是 10"], tool_calls=[{"name": "kitcalc", "args": {"x": 5}}])
    run = make_run(_toolagent, query="算 5*2", transport=t)
    out = await collect(_toolagent(run))
    assert "10" in out
    assert t.tool_invocations == [("kitcalc", {"x": 5}, {"v": 10})]


@pytest.mark.asyncio
async def test_kit_memory_roundtrip():
    t = FakeTransport()
    run = make_run(_rag, query="q", transport=t)
    await run.memory.set("pref", "简洁")
    assert await run.memory.get("pref") == "简洁"
    assert (await run.memory.all())["pref"] == "简洁"
