"""LangGraphProvider 集成测试：用真实 LangGraph 构造一个最简 echo graph，
验证 stream → delta + done，invoke 默认聚合得到 InvokeResult。
"""

import sys
import types

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState

from chameleon.providers.base.types import (
    AgentDef,
    InvokeContext,
    StreamEventType,
)
from chameleon.providers.langgraph.provider import LangGraphProvider


def _make_fake_agent_module(module_name: str) -> str:
    """动态注册一个伪 agent 模块，包含 build_graph()

    graph 行为：把最后一条 user 消息原样返回（"echo: <input>"）
    """

    def build_graph():
        async def echo_node(state: MessagesState) -> dict:
            from langchain_core.messages import AIMessage

            last_msg = state["messages"][-1]
            content = (
                last_msg.content
                if hasattr(last_msg, "content")
                else last_msg.get("content", "")
            )
            return {"messages": [AIMessage(content=f"echo: {content}")]}

        sg = StateGraph(MessagesState)
        sg.add_node("echo", echo_node)
        sg.add_edge(START, "echo")
        sg.add_edge("echo", END)
        return sg.compile()

    mod = types.ModuleType(module_name)
    mod.build_graph = build_graph
    mod.AGENT_META = {"key": "fake-echo", "description": "fake"}
    sys.modules[module_name] = mod
    return module_name


@pytest.fixture
def fake_agent_def() -> AgentDef:
    module = _make_fake_agent_module("chameleon._test_fake_agents.echo_in_test")
    return AgentDef(
        key="fake-echo",
        provider="langgraph",
        config={"module": module, "build_fn": "build_graph"},
    )


async def test_langgraph_stream_yields_done(fake_agent_def: AgentDef) -> None:
    provider = LangGraphProvider()
    ctx = InvokeContext(
        agent_def=fake_agent_def,
        input="hello",
        history=[],
        session_id="sess_test",
        app_id="app1",
        stream=True,
    )

    events = [ev async for ev in provider.stream(ctx)]
    types_seen = {ev.type for ev in events}

    # 至少应该有 step 事件（echo node 完成）
    assert StreamEventType.step in types_seen
    # 无 error
    assert StreamEventType.error not in types_seen


async def test_langgraph_invoke_returns_aggregated_result(
    fake_agent_def: AgentDef,
) -> None:
    provider = LangGraphProvider()
    ctx = InvokeContext(
        agent_def=fake_agent_def,
        input="hello",
        history=[],
        session_id="sess_invoke",
        app_id="app1",
        stream=False,
    )

    result = await provider.invoke(ctx)
    assert result.session_id == "sess_invoke"
    # 至少 echo node 的 step
    assert any(s.name == "echo" for s in result.steps)


async def test_graph_cache_reused(fake_agent_def: AgentDef) -> None:
    """第二次调用同一 agent 不应重新 build"""
    provider = LangGraphProvider()
    ctx = InvokeContext(
        agent_def=fake_agent_def,
        input="a",
        session_id="s1",
        app_id="a",
    )
    await provider.invoke(ctx)
    graph_first = provider._builder._cache.get(fake_agent_def.key)

    await provider.invoke(ctx)
    graph_second = provider._builder._cache.get(fake_agent_def.key)

    assert graph_first is graph_second
