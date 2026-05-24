"""LLMNode + KBNode 集成测试（P18.1 PR #18）

覆盖：
- LLMNode：string input / dict + template / messages list / KB joined_context 拼接
- KBNode：mock search_kb 验证 hits 透传 + joined_context 拼接
- 链式：start → KB → LLM → end 跑通；LLM 用到 KB 上下文
- 错误：KB kb_key 缺失 / template 缺字段
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from chameleon.core.graph import (
    EdgeSpec,
    GraphSpec,
    NodeContext,
    NodeSpec,
    NodeStatus,
)
from chameleon.core.graph.engine import Orchestrator
from chameleon.core.graph.nodes.llm import LLMNode
from chameleon.core.vector.base import ChunkHit


def _ctx() -> NodeContext:
    return NodeContext(
        request_id="rid-llm-kb",
        graph_id=1,
        graph_run_id=1,
        depth=0,
        started_at=datetime.now(timezone.utc),
    )


# ── LLMNode 输入形态测试（不真调 LLM） ──────────────────


class _FakeChatModel:
    """ainvoke 返回 mock AIMessage，含 content + usage_metadata"""

    def __init__(self, response: str = "stub answer", usage: dict | None = None):
        self._response = response
        self._usage = usage or {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
        }
        self.captured_messages: list = []
        self.model_name = "fake-model"

    async def ainvoke(self, messages, **kwargs) -> Any:
        self.captured_messages = list(messages)

        class _AIMsg:
            content = self._response
            usage_metadata = self._usage

        return _AIMsg()


@pytest.fixture
def fake_llm():
    from chameleon.core.components.llms import factory as llm_factory

    fake = _FakeChatModel("hello world", {"input_tokens": 3, "output_tokens": 2})
    llm_factory.set_for_test(fake)  # type: ignore[arg-type]
    yield fake
    llm_factory.set_for_test(None)


async def test_llm_node_string_input(fake_llm):
    node = LLMNode(NodeSpec(id="n", type="llm", data={}))
    out = await node.execute(_ctx(), "What is 1+1?")
    assert out["answer"] == "hello world"
    assert out["usage"]["prompt_tokens"] == 3
    assert out["usage"]["completion_tokens"] == 2
    assert out["usage"]["total_tokens"] == 5
    # 单条 HumanMessage
    assert len(fake_llm.captured_messages) == 1
    assert fake_llm.captured_messages[0].content == "What is 1+1?"


async def test_llm_node_dict_with_template(fake_llm):
    node = LLMNode(
        NodeSpec(
            id="n",
            type="llm",
            data={
                "system_prompt": "你是助手。",
                "prompt_template": "回答：{query}",
            },
        )
    )
    out = await node.execute(_ctx(), {"query": "中文吗？"})
    assert out["answer"] == "hello world"
    # 一条 system + 一条 human
    assert len(fake_llm.captured_messages) == 2
    assert fake_llm.captured_messages[0].content == "你是助手。"
    assert fake_llm.captured_messages[1].content == "回答：中文吗？"


async def test_llm_node_template_missing_field(fake_llm):
    node = LLMNode(
        NodeSpec(
            id="n",
            type="llm",
            data={"prompt_template": "{missing}"},
        )
    )
    with pytest.raises(ValueError, match="prompt_template 渲染失败"):
        await node.execute(_ctx(), {"query": "x"})


async def test_llm_node_messages_list_input(fake_llm):
    node = LLMNode(NodeSpec(id="n", type="llm", data={}))
    out = await node.execute(
        _ctx(),
        [
            {"role": "system", "content": "S"},
            {"role": "user", "content": "U"},
            {"role": "assistant", "content": "A"},
        ],
    )
    assert out["answer"] == "hello world"
    assert len(fake_llm.captured_messages) == 3
    # AIMessage / HumanMessage / SystemMessage 类型校验
    assert fake_llm.captured_messages[0].type == "system"
    assert fake_llm.captured_messages[2].type == "ai"


async def test_llm_node_uses_kb_joined_context(fake_llm):
    """KBNode → LLMNode：joined_context 自动拼成 'Reference: ... Q: ...'"""
    node = LLMNode(NodeSpec(id="n", type="llm", data={}))
    out = await node.execute(
        _ctx(),
        {
            "query": "what is foo?",
            "joined_context": "foo is bar.\n\nbaz is qux.",
        },
    )
    assert out["answer"] == "hello world"
    assert len(fake_llm.captured_messages) == 1
    content = fake_llm.captured_messages[0].content
    assert "foo is bar" in content
    assert "what is foo?" in content


async def test_llm_node_temperature_validation():
    with pytest.raises(ValueError, match="temperature 必须"):
        LLMNode(NodeSpec(id="n", type="llm", data={"temperature": 3.0}))


# ── A3：dict input 不再因 "type=dict" 抛错 ─────────────────


async def test_llm_node_dict_upstream_answer_field(fake_llm):
    """上游 LLM 节点输出 {answer: ...} 直接喂给下游 LLM 节点（无 template）"""
    node = LLMNode(NodeSpec(id="n", type="llm", data={}))
    out = await node.execute(
        _ctx(),
        {"answer": "上一步的结论", "tool_calls": [], "usage": None, "model": "x"},
    )
    assert out["answer"] == "hello world"
    assert len(fake_llm.captured_messages) == 1
    assert fake_llm.captured_messages[0].content == "上一步的结论"


async def test_llm_node_dict_no_known_field_json_fallback(fake_llm):
    """dict 无任何已知字段（如 tool 节点结构化输出）→ JSON 兜底，不再抛错"""
    node = LLMNode(NodeSpec(id="n", type="llm", data={}))
    tool_output = {"tool_key": "http", "ok": True, "data": {"status": 200}}
    out = await node.execute(_ctx(), tool_output)
    assert out["answer"] == "hello world"
    assert len(fake_llm.captured_messages) == 1
    content = fake_llm.captured_messages[0].content
    # 兜底把整个 dict 序列化成 JSON，字段都在
    assert "tool_key" in content
    assert "200" in content


def test_build_messages_dict_never_raises_on_dict():
    """回归：任意 dict（含空 dict）都不再抛 '无法从 input 构造 messages：type=dict'"""
    from chameleon.core.graph.nodes.llm import _build_messages

    for bad in ({}, {"foo": 1}, {"nested": {"a": [1, 2]}}):
        msgs = _build_messages(bad, None, None)
        assert len(msgs) == 1
        assert msgs[0].type == "human"


# ── KBNode 测试（mock search_kb） ───────────────────────


async def test_kb_node_basic():
    """KBNode 透传 hits + joined_context"""
    from chameleon.core.graph.nodes.kb import KBNode

    fake_hits = [
        ChunkHit(
            id=1,
            doc_id=10,
            seq=1,
            content="chunk one",
            score=0.95,
            meta=None,
        ),
        ChunkHit(
            id=2,
            doc_id=10,
            seq=2,
            content="chunk two",
            score=0.85,
            meta=None,
        ),
    ]
    node = KBNode(
        NodeSpec(id="kb", type="kb", data={"kb_key": "demo", "top_k": 3})
    )
    with patch(
        "chameleon.core.components.inventory.search_kb",
        new=AsyncMock(return_value=fake_hits),
    ) as mock_search:
        out = await node.execute(_ctx(), {"query": "anything"})
    mock_search.assert_awaited_once_with(
        "demo", "anything", top_k=3, min_score=0.0
    )
    assert len(out["hits"]) == 2
    assert out["hits"][0]["content"] == "chunk one"
    assert out["joined_context"] == "chunk one\n\nchunk two"
    assert out["top_k"] == 3


async def test_kb_node_missing_kb_key():
    from chameleon.core.graph.nodes.kb import KBNode

    with pytest.raises(ValueError, match="kb_key 必填"):
        KBNode(NodeSpec(id="kb", type="kb", data={}))


async def test_kb_node_picks_query_from_answer_field():
    """上游 LLM 返 {answer: '...'}; KBNode 也能用作 query"""
    from chameleon.core.graph.nodes.kb import KBNode

    node = KBNode(NodeSpec(id="kb", type="kb", data={"kb_key": "demo"}))
    with patch(
        "chameleon.core.components.inventory.search_kb",
        new=AsyncMock(return_value=[]),
    ) as mock_search:
        await node.execute(_ctx(), {"answer": "look this up"})
    mock_search.assert_awaited_once()
    assert mock_search.call_args[0][1] == "look this up"


# ── 端到端：start → KB → LLM → end ────────────────────


async def test_chain_kb_then_llm(fake_llm):
    """完整图：start → KB → LLM → end；LLM 接到 joined_context"""
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="kb", type="kb", data={"kb_key": "demo", "top_k": 2}),
            NodeSpec(
                id="llm",
                type="llm",
                data={"system_prompt": "答简短"},
            ),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="kb"),
            EdgeSpec(id="2", source="kb", target="llm"),
            EdgeSpec(id="3", source="llm", target="e"),
        ],
    )
    fake_hits = [
        ChunkHit(id=1, doc_id=10, seq=1, content="天空是蓝色的", score=0.9),
        ChunkHit(id=2, doc_id=10, seq=2, content="因为瑞利散射", score=0.8),
    ]
    executor = Orchestrator(spec)
    with patch(
        "chameleon.core.components.inventory.search_kb",
        new=AsyncMock(return_value=fake_hits),
    ):
        result = await executor.run(
            input={"query": "天空为什么蓝？"}, ctx=_ctx()
        )

    assert result.status == NodeStatus.SUCCESS
    assert result.output["answer"] == "hello world"
    # LLM 节点的 captured messages 应有 system + 一条含 joined_context 的 human
    assert len(fake_llm.captured_messages) == 2
    human_msg = fake_llm.captured_messages[1].content
    assert "天空是蓝色的" in human_msg
    assert "天空为什么蓝？" in human_msg
