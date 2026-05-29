"""LLMNode A2：流式 / Memory buffer / 多轮 tool_call 单测

不真调 LLM（set_for_test 注入 fake）；工具执行 patch run_tool（工具本身的
执行细节由 tool.py / ToolNode 测试覆盖，这里只验 agentic 循环编排）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from chameleon.core.api.sse_events import SSEEventKind
from chameleon.engine.graph import EdgeSpec, GraphSpec, NodeContext, NodeSpec
from chameleon.engine.graph.engine import Orchestrator
from chameleon.engine.graph.nodes.llm import LLMNode
from chameleon.engine.graph.nodes.llm_messages import build_messages


def _ctx() -> NodeContext:
    return NodeContext(
        request_id="rid-a2",
        graph_id=1,
        graph_run_id=1,
        depth=0,
        started_at=datetime.now(timezone.utc),
    )


# ── Memory buffer（build_messages 直测）────────────────────


def test_memory_window_keeps_recent_messages():
    history = [{"role": "user", "content": f"m{i}"} for i in range(5)]
    msgs = build_messages(history, None, None, memory_window=2)
    assert len(msgs) == 2
    assert [m.content for m in msgs] == ["m3", "m4"]


def test_memory_window_none_keeps_all():
    history = [{"role": "user", "content": f"m{i}"} for i in range(4)]
    msgs = build_messages(history, None, None, memory_window=None)
    assert len(msgs) == 4


def test_memory_dict_history_plus_query():
    inp = {
        "history": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "yo"},
        ],
        "query": "下一题？",
    }
    msgs = build_messages(inp, "你是助手", None, memory_window=10)
    # system + 2 history + 1 current query
    assert len(msgs) == 4
    assert msgs[0].type == "system"
    assert msgs[1].content == "hi"
    assert msgs[2].content == "yo"
    assert msgs[-1].type == "human"
    assert msgs[-1].content == "下一题？"


def test_memory_dict_history_windowed_then_query():
    inp = {
        "history": [{"role": "user", "content": f"t{i}"} for i in range(6)],
        "query": "now",
    }
    msgs = build_messages(inp, None, None, memory_window=2)
    # 历史窗口 2 条 + 当前 query
    assert len(msgs) == 3
    assert [m.content for m in msgs] == ["t4", "t5", "now"]


# ── 流式（execute_stream）───────────────────────────────────


class _FakeStreamModel:
    """astream 逐 token 吐 AIMessageChunk；ainvoke 返完整 AIMessage"""

    model_name = "fake-stream"

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens

    async def astream(self, messages, **kwargs):
        for t in self._tokens:
            yield AIMessageChunk(content=t)

    async def ainvoke(self, messages, **kwargs):
        return AIMessage(content="".join(self._tokens))


@pytest.fixture
def fake_stream():
    from chameleon.integrations.llms import factory as llm_factory

    fake = _FakeStreamModel(["Hel", "lo", " 世界"])
    llm_factory.set_for_test(fake)  # type: ignore[arg-type]
    yield fake
    llm_factory.set_for_test(None)


async def test_execute_stream_emits_token_deltas(fake_stream):
    deltas: list[str] = []

    async def emit(text: str) -> None:
        deltas.append(text)

    node = LLMNode(NodeSpec(id="n", type="llm", data={}))
    out = await node.execute_stream(_ctx(), "hi", emit)

    assert deltas == ["Hel", "lo", " 世界"]
    assert out["answer"] == "Hello 世界"
    assert out["rounds_used"] == 1
    assert out["tool_calls"] == []


async def test_execute_batch_no_emit(fake_stream):
    """execute()（emit=None）走 ainvoke，不流式但结果一致"""
    node = LLMNode(NodeSpec(id="n", type="llm", data={}))
    out = await node.execute(_ctx(), "hi")
    assert out["answer"] == "Hello 世界"


async def test_run_streaming_graph_emits_node_delta(fake_stream):
    """A1+A2 集成：graph 流式跑，LLM 节点逐 token 发 graph.node.delta"""
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="llm", type="llm", data={}),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="llm"),
            EdgeSpec(id="2", source="llm", target="e"),
        ],
    )
    orch = Orchestrator(spec)
    events = [
        ev async for ev in orch.run_streaming(input={"query": "hi"}, ctx=_ctx())
    ]
    deltas = [
        ev[SSEEventKind.GRAPH_NODE_DELTA.value]
        for ev in events
        if SSEEventKind.GRAPH_NODE_DELTA.value in ev
    ]
    assert [d["delta"] for d in deltas] == ["Hel", "lo", " 世界"]
    assert all(d["node_id"] == "llm" for d in deltas)


# ── 多轮 tool_call（agentic 循环）──────────────────────────


class _FakeToolLoopModel:
    """round 1 返 tool_call；round 2 返最终答案（验 ≥2 轮）"""

    model_name = "fake-tool"

    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, messages, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "echo_tool",
                        "args": {"x": 1},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(
            content="最终答案",
            usage_metadata={
                "input_tokens": 5,
                "output_tokens": 3,
                "total_tokens": 8,
            },
        )


@pytest.fixture
def fake_tool_loop():
    from chameleon.integrations.llms import factory as llm_factory

    fake = _FakeToolLoopModel()
    llm_factory.set_for_test(fake)  # type: ignore[arg-type]
    yield fake
    llm_factory.set_for_test(None)


async def test_multi_round_tool_call(fake_tool_loop):
    node = LLMNode(
        NodeSpec(
            id="n",
            type="llm",
            data={"tool_keys": ["echo_tool"], "max_tool_rounds": 3},
        )
    )
    with patch(
        "chameleon.engine.graph.nodes.llm_tools.run_tool",
        new=AsyncMock(
            return_value={"tool_key": "echo_tool", "ok": True, "data": {"x": 1}}
        ),
    ) as mock_run:
        out = await node.execute(_ctx(), {"query": "调用工具"})

    # 跑了 2 轮：round1 工具 → round2 最终答案
    assert out["rounds_used"] == 2
    assert out["answer"] == "最终答案"
    assert fake_tool_loop.calls == 2
    mock_run.assert_awaited_once()

    # tool_rounds 记录 1 个工具回合
    assert len(out["tool_rounds"]) == 1
    rnd = out["tool_rounds"][0]
    assert rnd["round"] == 1
    assert rnd["tool_calls"][0]["name"] == "echo_tool"
    assert rnd["tool_results"][0]["result"]["ok"] is True
    # 最终轮无 tool_call
    assert out["tool_calls"] == []


async def test_tool_loop_respects_max_rounds():
    """模型每轮都要工具 → 达 max_tool_rounds 即停（防无限循环）"""
    from chameleon.integrations.llms import factory as llm_factory

    class _AlwaysToolModel:
        model_name = "always-tool"

        async def ainvoke(self, messages, **kwargs):
            return AIMessage(
                content="thinking",
                tool_calls=[
                    {"name": "t", "args": {}, "id": "c", "type": "tool_call"}
                ],
            )

    llm_factory.set_for_test(_AlwaysToolModel())  # type: ignore[arg-type]
    try:
        node = LLMNode(
            NodeSpec(
                id="n",
                type="llm",
                data={"tool_keys": ["t"], "max_tool_rounds": 2},
            )
        )
        with patch(
            "chameleon.engine.graph.nodes.llm_tools.run_tool",
            new=AsyncMock(return_value={"tool_key": "t", "ok": True, "data": None}),
        ):
            out = await node.execute(_ctx(), {"query": "x"})
    finally:
        llm_factory.set_for_test(None)

    assert out["rounds_used"] == 2
    assert len(out["tool_rounds"]) == 2  # 两轮都进了工具
    assert out["answer"] == "thinking"  # 兜底用最后一轮内容


def test_validate_max_tool_rounds_cap():
    with pytest.raises(ValueError, match="max_tool_rounds"):
        LLMNode(NodeSpec(id="n", type="llm", data={"max_tool_rounds": 99}))


def test_validate_memory_window():
    with pytest.raises(ValueError, match="memory_window"):
        LLMNode(NodeSpec(id="n", type="llm", data={"memory_window": 0}))
