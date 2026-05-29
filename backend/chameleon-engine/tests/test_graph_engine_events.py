"""GraphEngine SSE 事件发射单测（v1.1 PR A1）

覆盖：
- GraphEventManager：emit / stream / close 基本语义 + close 后 emit 忽略
- Orchestrator.run_streaming：链式图发 graph.started → 每节点 started/finished
  → graph.finished(success)
- 失败节点发 graph.node.failed + graph.finished(failed)
- 所有 wire kind 都是 SSEEventKind 成员（红线：禁止匿名 event）
- events=None 时 run() 行为不变（不发任何事件）
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from chameleon.core.api.sse_events import SSEEventKind
from chameleon.engine.graph import (
    EdgeSpec,
    GraphSpec,
    Node,
    NodeContext,
    NodeSpec,
    NodeStatus,
)
from chameleon.engine.graph.engine import GraphEventManager, Orchestrator
from chameleon.engine.graph.engine.event_manager import (
    GraphNodeEventPayload,
    event_graph_node_started,
)
from chameleon.engine.graph.registry import register_node_type

# ── 测试用节点（唯一 type 名，避免与其它测试文件 registry 冲突）──────


class _EvEchoNode(Node[Any, Any]):
    type = "_ev_echo"

    async def execute(self, ctx: NodeContext, input: Any) -> Any:
        return {"echoed": input, "node": self.id}


class _EvBoomNode(Node[Any, Any]):
    type = "_ev_boom"

    async def execute(self, ctx: NodeContext, input: Any) -> Any:
        raise RuntimeError("kaboom")


register_node_type(_EvEchoNode)
register_node_type(_EvBoomNode)


def _ctx() -> NodeContext:
    return NodeContext(
        request_id="rid-ev",
        graph_id=7,
        graph_run_id=0,
        depth=0,
        started_at=datetime.now(timezone.utc),
    )


# ── GraphEventManager ────────────────────────────────────


async def test_event_manager_emit_stream_close():
    em = GraphEventManager()
    await em.emit({"a": 1})
    await em.emit({"b": 2})
    await em.close()
    got = [ev async for ev in em.stream()]
    assert got == [{"a": 1}, {"b": 2}]


async def test_event_manager_emit_after_close_ignored():
    em = GraphEventManager()
    await em.close()
    await em.emit({"late": 1})  # 应被忽略
    got = [ev async for ev in em.stream()]
    assert got == []


# ── helper：把扁平事件 dict 拆成 (kind, payload) ──────────────


def _kind(ev: dict[str, Any]) -> str:
    assert len(ev) == 1, f"事件 dict 必须单 key：{ev}"
    return next(iter(ev))


# ── Orchestrator.run_streaming ───────────────────────────


def _chain_spec() -> GraphSpec:
    return GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="m", type="_ev_echo", name="middle"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="m"),
            EdgeSpec(id="2", source="m", target="e"),
        ],
    )


async def test_run_streaming_emits_node_lifecycle():
    orch = Orchestrator(_chain_spec())
    events = [
        ev
        async for ev in orch.run_streaming(input={"hi": 1}, ctx=_ctx())
    ]
    kinds = [_kind(ev) for ev in events]

    # 首个 graph.started，末个 graph.finished
    assert kinds[0] == SSEEventKind.GRAPH_STARTED.value
    assert kinds[-1] == SSEEventKind.GRAPH_FINISHED.value

    # 每个节点都有 started + finished
    started = [
        ev[SSEEventKind.GRAPH_NODE_STARTED.value]
        for ev in events
        if _kind(ev) == SSEEventKind.GRAPH_NODE_STARTED.value
    ]
    finished = [
        ev[SSEEventKind.GRAPH_NODE_FINISHED.value]
        for ev in events
        if _kind(ev) == SSEEventKind.GRAPH_NODE_FINISHED.value
    ]
    assert {n["node_id"] for n in started} == {"s", "m", "e"}
    assert {n["node_id"] for n in finished} == {"s", "m", "e"}

    # finished 携带 status + duration + output
    mid = next(n for n in finished if n["node_id"] == "m")
    assert mid["status"] == NodeStatus.SUCCESS.value
    assert mid["node_type"] == "_ev_echo"
    assert mid["name"] == "middle"
    assert "duration_ms" in mid
    assert mid["output"] == {"echoed": {"hi": 1}, "node": "m"}

    # graph.finished 摘要
    summary = events[-1][SSEEventKind.GRAPH_FINISHED.value]
    assert summary["status"] == NodeStatus.SUCCESS.value
    assert summary["node_count"] == 3


async def test_run_streaming_failed_node_emits_failed():
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="b", type="_ev_boom"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="b"),
            EdgeSpec(id="2", source="b", target="e"),
        ],
    )
    orch = Orchestrator(spec)
    events = [ev async for ev in orch.run_streaming(input={}, ctx=_ctx())]
    kinds = [_kind(ev) for ev in events]

    assert SSEEventKind.GRAPH_NODE_FAILED.value in kinds
    failed = next(
        ev[SSEEventKind.GRAPH_NODE_FAILED.value]
        for ev in events
        if _kind(ev) == SSEEventKind.GRAPH_NODE_FAILED.value
    )
    assert failed["node_id"] == "b"
    assert failed["status"] == NodeStatus.FAILED.value
    assert failed["error"]["type"] == "RuntimeError"
    assert "kaboom" in failed["error"]["message"]

    summary = events[-1][SSEEventKind.GRAPH_FINISHED.value]
    assert summary["status"] == NodeStatus.FAILED.value


async def test_all_streaming_kinds_are_registered():
    """红线回归：流里出现的每个 kind 都是 SSEEventKind 成员（无匿名 event）"""
    valid = {k.value for k in SSEEventKind}
    orch = Orchestrator(_chain_spec())
    async for ev in orch.run_streaming(input={"x": 1}, ctx=_ctx()):
        assert _kind(ev) in valid


async def test_run_without_events_is_silent():
    """events=None：run() 不发事件、结果与 batch 模式一致"""
    orch = Orchestrator(_chain_spec())
    result = await orch.run(input={"hi": 1}, ctx=_ctx())
    assert result.status == NodeStatus.SUCCESS
    assert result.output == {"echoed": {"hi": 1}, "node": "m"}


def test_event_builders_reference_typed_kinds():
    ev = event_graph_node_started(GraphNodeEventPayload(node_id="x"))
    assert _kind(ev) == SSEEventKind.GRAPH_NODE_STARTED.value
    assert ev[SSEEventKind.GRAPH_NODE_STARTED.value]["node_id"] == "x"
