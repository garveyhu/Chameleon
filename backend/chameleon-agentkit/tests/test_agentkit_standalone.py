"""StandaloneTransport 单测：脱平台跑 @agent（作者自带模型 + 本地 memory/kb/子agent/ReAct）。"""

from __future__ import annotations

import pytest

from chameleon.agentkit import AgentRun, ModelSlot, agent, tool
from chameleon.agentkit._spec import Doc
from chameleon.agentkit.standalone import StandaloneTransport, run_standalone


class _Msg:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _StructuredFake:
    def __init__(self, value):
        self._value = value

    async def ainvoke(self, messages, **_kw):
        return self._value


class _FakeModel:
    """鸭子类型 LangChain chat model：ainvoke/astream/with_structured_output/bind_tools。"""

    def __init__(self, *, answer="完整答案", chunks=None, tool_rounds=None, structured=None):
        self._answer = answer
        self._chunks = chunks if chunks is not None else ["完整", "答案"]
        self._tool_rounds = list(tool_rounds or [])
        self._round = 0
        self._structured = structured

    async def ainvoke(self, messages, **_kw):
        if self._round < len(self._tool_rounds):
            tc = self._tool_rounds[self._round]
            self._round += 1
            if tc:
                return _Msg(tool_calls=tc)
        return _Msg(content=self._answer)

    async def astream(self, messages, **_kw):
        for c in self._chunks:
            yield _Msg(content=c)

    def with_structured_output(self, schema):
        return _StructuredFake(self._structured)

    def bind_tools(self, tools):
        return self


@pytest.mark.asyncio
async def test_standalone_complete_and_stream():
    @agent(key="sa-hello", name="hi", models=[ModelSlot("chat", "对话")])
    async def handle(ctx: AgentRun):
        async for d in ctx.stream(system="s", user=ctx.query):
            yield d

    t = StandaloneTransport(model=_FakeModel(chunks=["你", "好"]))
    out = await run_standalone(handle, "hi", transport=t)
    assert out == "你好"  # 脱平台、作者自带模型流式跑通


@pytest.mark.asyncio
async def test_standalone_memory_local():
    @agent(key="sa-mem", name="m", models=[ModelSlot("chat", "对话")])
    async def handle(ctx: AgentRun):
        prev = await ctx.memory.get("seen", 0)
        await ctx.memory.set("seen", prev + 1)
        yield f"seen={prev + 1}"

    t = StandaloneTransport(model=_FakeModel())
    assert await run_standalone(handle, "x", transport=t) == "seen=1"
    assert await run_standalone(handle, "x", transport=t) == "seen=2"  # 本地记忆跨调用持久


@pytest.mark.asyncio
async def test_standalone_kb_local_search():
    docs = [Doc(text="北京 今天 晴天"), Doc(text="上海 阴天 有雨")]
    t = StandaloneTransport(model=_FakeModel(), kb_docs=docs)

    @agent(key="sa-kb", name="k", kb=True, models=[ModelSlot("chat", "对话")])
    async def handle(ctx: AgentRun):
        hits = await ctx.kb.search("北京 晴天")
        yield hits[0].text if hits else "无"

    assert await run_standalone(handle, "北京天气", transport=t) == "北京 今天 晴天"


@pytest.mark.asyncio
async def test_standalone_media_raises_platform_only():
    @agent(key="sa-media", name="md", models=[ModelSlot("chat", "对话")])
    async def handle(ctx: AgentRun):
        await ctx.media.generate(kind="image", prompt="cat")
        yield "x"

    t = StandaloneTransport(model=_FakeModel())
    with pytest.raises(NotImplementedError, match="平台专属"):
        await run_standalone(handle, "q", transport=t)


@pytest.mark.asyncio
async def test_standalone_call_agent_local_registry():
    @agent(key="sa-sub", name="sub", models=[ModelSlot("chat", "对话")])
    async def sub(ctx: AgentRun):
        yield f"子处理:{ctx.query}"

    @agent(key="sa-main", name="main", models=[ModelSlot("chat", "对话")], call_agents=["sa-sub"])
    async def main(ctx: AgentRun):
        ans = await ctx.call_agent("sa-sub", input=ctx.query)
        yield f"主包装[{ans}]"

    t = StandaloneTransport(model=_FakeModel(), agents={"sa-sub": sub})
    out = await run_standalone(main, "任务", transport=t)
    assert out == "主包装[子处理:任务]"  # 本地子 agent A2A 脱平台跑通


@pytest.mark.asyncio
async def test_standalone_react_tool_loop():
    @tool(name="add", description="加法")
    async def add(a: int, b: int) -> int:
        return a + b

    @agent(key="sa-react", name="r", models=[ModelSlot("chat", "对话")])
    async def handle(ctx: AgentRun):
        async for d in ctx.run_with_tools(user=ctx.query, tools=[add]):
            yield d

    # 第 1 轮模型出 tool_call(add)，第 2 轮无 call → 出最终答案
    model = _FakeModel(
        answer="结果是3",
        tool_rounds=[[{"name": "add", "args": {"a": 1, "b": 2}, "id": "c1"}], []],
    )
    t = StandaloneTransport(model=model)
    out = await run_standalone(handle, "1+2", transport=t)
    assert out == "结果是3"  # 真 ReAct：bind 工具→执行→回填→最终答案
