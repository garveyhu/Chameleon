"""LocalProvider 集成测试：BaseAgent 子类范式

构造一个动态注册的 BaseAgent 子类，通过 LocalProvider.stream() 跑通
LangGraph CompiledGraph 编排。
"""

import sys
import types

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState

from chameleon.core.base import AgentMetadata, BaseAgent
from chameleon.providers.base.types import AgentDef, InvokeContext, StreamEventType
from chameleon.providers.local.provider import LocalProvider


def _make_fake_agent_module(module_name: str, agent_id: str) -> tuple[str, type]:
    """动态注册一个伪 BaseAgent 子类模块"""

    def build_graph_fn():
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

    class FakeAgent(BaseAgent):
        @classmethod
        def get_metadata(cls) -> AgentMetadata:
            return AgentMetadata(id=agent_id, name="Fake", description="fake")

        @classmethod
        def build_graph(cls):
            return build_graph_fn()

    mod = types.ModuleType(module_name)
    mod.FakeAgent = FakeAgent
    FakeAgent.__module__ = module_name
    sys.modules[module_name] = mod
    return module_name, FakeAgent


@pytest.fixture
def fake_agent_def() -> AgentDef:
    module, cls = _make_fake_agent_module(
        "chameleon._test_fake_agents.echo_in_test", "fake-echo"
    )
    return AgentDef(
        key="fake-echo",
        provider="local",
        config={"module": module, "agent_class": cls.__name__},
    )


async def test_local_provider_stream_yields_step(fake_agent_def: AgentDef) -> None:
    provider = LocalProvider()
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

    assert StreamEventType.step in types_seen
    assert StreamEventType.error not in types_seen


async def test_local_provider_invoke_aggregates(fake_agent_def: AgentDef) -> None:
    provider = LocalProvider()
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
    assert any(s.name == "echo" for s in result.steps)


async def test_local_provider_name() -> None:
    """LocalProvider.name = 'local'"""
    assert LocalProvider.name == "local"


def test_langgraph_provider_alias() -> None:
    """v0.1 兼容：LangGraphProvider 仍然指向 LocalProvider"""
    from chameleon.providers.local.provider import LangGraphProvider

    assert LangGraphProvider is LocalProvider
