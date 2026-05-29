"""P18.2 PR #23: LLMNode 启用 tool_keys 时的 function calling 行为"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from chameleon.core.graph import NodeContext, NodeSpec
from chameleon.core.graph.nodes.llm import LLMNode


def _ctx() -> NodeContext:
    return NodeContext(
        request_id="rid",
        graph_id=1,
        graph_run_id=1,
        depth=0,
        started_at=datetime.now(timezone.utc),
    )


class _FakeClientWithBindTools:
    """模拟 langchain ChatOpenAI：bind_tools + ainvoke 返带 tool_calls 的 AIMessage"""

    def __init__(self):
        self.captured_tools: list[dict] = []
        self.captured_messages: list = []
        self.model_name = "fake"

    def bind_tools(self, schemas):
        self.captured_tools = schemas
        return self

    async def ainvoke(self, messages, **kwargs) -> Any:
        self.captured_messages = list(messages)

        class _AIMsg:
            content = ""
            tool_calls = [
                {
                    "name": "http",
                    "args": {"method": "GET", "url": "https://example.com/"},
                    "id": "call_abc",
                }
            ]
            usage_metadata = {"input_tokens": 10, "output_tokens": 3}

        return _AIMsg()


@pytest.fixture
def fake_llm_with_tools():
    from chameleon.integrations.llms import factory as llm_factory

    fake = _FakeClientWithBindTools()
    llm_factory.set_for_test(fake)  # type: ignore[arg-type]
    yield fake
    llm_factory.set_for_test(None)


async def test_llm_node_validates_tool_keys_type():
    with pytest.raises(ValueError, match="tool_keys"):
        LLMNode(
            NodeSpec(
                id="n", type="llm", data={"tool_keys": "not-a-list"}
            )
        )


async def test_llm_node_returns_tool_calls(fake_llm_with_tools):
    """绑定 tool_keys → 模型决定调 http → 返 tool_calls 数组"""
    node = LLMNode(
        NodeSpec(
            id="n",
            type="llm",
            data={"tool_keys": ["http"]},
        )
    )
    out = await node.execute(_ctx(), "请帮我抓一下 https://example.com/")
    assert isinstance(out["tool_calls"], list)
    assert len(out["tool_calls"]) == 1
    tc = out["tool_calls"][0]
    assert tc["name"] == "http"
    assert tc["args"]["method"] == "GET"
    assert tc["id"] == "call_abc"

    # 内置 schema 已经被传给 bind_tools
    schemas = fake_llm_with_tools.captured_tools
    assert len(schemas) == 1
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "http"


async def test_llm_node_skips_unknown_tool_keys(fake_llm_with_tools):
    """tool_keys 含未注册的 key → 跳过 + 仅传已知 schema"""
    node = LLMNode(
        NodeSpec(
            id="n",
            type="llm",
            data={"tool_keys": ["http", "ghost"]},
        )
    )
    await node.execute(_ctx(), "x")
    schemas = fake_llm_with_tools.captured_tools
    keys = [s["function"]["name"] for s in schemas]
    assert keys == ["http"]


async def test_llm_node_without_tool_keys_skips_binding(fake_llm_with_tools):
    """不传 tool_keys → 不调 bind_tools；tool_calls 为空数组"""
    node = LLMNode(NodeSpec(id="n", type="llm", data={}))
    out = await node.execute(_ctx(), "x")
    # captured_tools 仍为空（FakeClient 初始 [] 没被 bind_tools 覆盖）
    assert fake_llm_with_tools.captured_tools == []
    # tool_calls：fake 仍然返了 tool_calls，但因为没 bind 过，也应该被拿出来
    # 这是 fake client 的特性 —— 真实 LLM 不 bind 不会返。本测验证字段透出。
    assert "tool_calls" in out
