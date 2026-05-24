"""ReadyQueue + GraphExecState 单测（v1.1 PR88 第一波）

验证：
- 5 节点串行图：ready 序 == 拓扑序
- 入度 > 1 的节点（join）：所有上游完成才入队
- if_else 分支：未选中分支整条 skip（不会出现在 ready 序）
- VariablePool / GraphExecState 并发安全 + snapshot 一致
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from chameleon.core.graph.engine import GraphExecState, ReadyQueue, VariablePool
from chameleon.core.graph.node_base import NodeStatus
from chameleon.core.graph.types import EdgeSpec, GraphSpec, NodeSpec


def _make_node(nid: str, ntype: str = "noop") -> NodeSpec:
    return NodeSpec(id=nid, type=ntype, name=nid)


def _make_edge(eid: str, src: str, tgt: str, handle: str | None = None) -> EdgeSpec:
    return EdgeSpec(id=eid, source=src, target=tgt, source_handle=handle)


# ── 5 节点串行图：start → a → b → c → end ───────────────────


def _serial_spec_5() -> GraphSpec:
    return GraphSpec(
        nodes=[
            _make_node("start", "start"),
            _make_node("a"),
            _make_node("b"),
            _make_node("c"),
            _make_node("end", "end"),
        ],
        edges=[
            _make_edge("e1", "start", "a"),
            _make_edge("e2", "a", "b"),
            _make_edge("e3", "b", "c"),
            _make_edge("e4", "c", "end"),
        ],
    )


async def _drain_serial(rq: ReadyQueue) -> list[str]:
    """串行消费：每次 get → 立刻 mark_done"""
    order: list[str] = []
    while not rq.is_drained():
        nid = await rq.get()
        order.append(nid)
        await rq.mark_done(nid)
    return order


@pytest.mark.asyncio
async def test_ready_queue_serial_5_nodes() -> None:
    rq = ReadyQueue(_serial_spec_5())
    # 初始只有 start 入队
    assert rq._peek_queue_size() == 1
    order = await _drain_serial(rq)
    assert order == ["start", "a", "b", "c", "end"]
    assert rq.is_drained()


# ── 菱形 (diamond) join：start → (a, b) → c → end ───────────


def _diamond_spec() -> GraphSpec:
    return GraphSpec(
        nodes=[
            _make_node("start", "start"),
            _make_node("a"),
            _make_node("b"),
            _make_node("c"),
            _make_node("end", "end"),
        ],
        edges=[
            _make_edge("e1", "start", "a"),
            _make_edge("e2", "start", "b"),
            _make_edge("e3", "a", "c"),
            _make_edge("e4", "b", "c"),
            _make_edge("e5", "c", "end"),
        ],
    )


@pytest.mark.asyncio
async def test_ready_queue_diamond_c_waits_for_both_parents() -> None:
    rq = ReadyQueue(_diamond_spec())

    # 初始只有 start
    assert (await rq.get()) == "start"
    await rq.mark_done("start")

    # start 完成后 a, b 都入队
    first = await rq.get()
    await rq.mark_done(first)
    # c 还不该入队（另一个 parent 未完成）
    assert rq._peek_remaining_in("c") == 1

    second = await rq.get()
    assert {first, second} == {"a", "b"}
    await rq.mark_done(second)
    # 现在 c 应该 ready
    assert (await rq.get()) == "c"
    await rq.mark_done("c")

    assert (await rq.get()) == "end"
    await rq.mark_done("end")
    assert rq.is_drained()


# ── if_else 分支：start → if → (true_branch / false_branch) → end ─


def _if_else_spec() -> GraphSpec:
    return GraphSpec(
        nodes=[
            _make_node("start", "start"),
            _make_node("cond", "if_else"),
            _make_node("yes"),
            _make_node("no"),
            _make_node("end", "end"),
        ],
        edges=[
            _make_edge("e1", "start", "cond"),
            _make_edge("e2", "cond", "yes", handle="true"),
            _make_edge("e3", "cond", "no", handle="false"),
            _make_edge("e4", "yes", "end"),
            _make_edge("e5", "no", "end"),
        ],
    )


@pytest.mark.asyncio
async def test_ready_queue_if_else_skips_unselected_branch() -> None:
    rq = ReadyQueue(_if_else_spec())
    order: list[str] = []

    nid = await rq.get()
    order.append(nid)
    await rq.mark_done(nid)
    assert nid == "start"

    nid = await rq.get()
    order.append(nid)
    # 走 true 分支：'no' 整条 skip
    await rq.mark_done(nid, selected_handle="true")
    assert nid == "cond"

    nid = await rq.get()
    order.append(nid)
    await rq.mark_done(nid)
    assert nid == "yes"

    # end 节点入度 2，但 'no' 被 skip 后入度也归 0 → 走完 yes 后 end ready
    nid = await rq.get()
    order.append(nid)
    await rq.mark_done(nid)
    assert nid == "end"

    assert "no" not in order
    assert rq.is_drained()


# ── 失败节点不传播 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_ready_queue_failed_node_stops_propagation() -> None:
    rq = ReadyQueue(_serial_spec_5())
    assert (await rq.get()) == "start"
    await rq.mark_done("start")
    assert (await rq.get()) == "a"
    # a 失败：不传播给 b
    await rq.mark_done("a", success=False)
    # 此时队列空、in_flight=0、但 b/c/end 入度仍 > 0
    assert rq.is_drained()
    assert rq._peek_remaining_in("b") == 1


# ── VariablePool 并发写 + snapshot 一致 ────────────────────


@pytest.mark.asyncio
async def test_variable_pool_concurrent_writes() -> None:
    pool = VariablePool()

    async def writer(i: int) -> None:
        await pool.set_output(f"node_{i}", {"value": i})

    await asyncio.gather(*(writer(i) for i in range(50)))
    snap = await pool.snapshot()
    assert len(snap["outputs"]) == 50
    assert snap["outputs"]["node_42"] == {"value": 42}


# ── GraphExecState 状态机 + deadline ─────────────────────


@pytest.mark.asyncio
async def test_graph_exec_state_status_transitions() -> None:
    st = GraphExecState.create(graph_id=1, run_id="run_xxx")
    assert (await st.get_status("a")) == NodeStatus.PENDING
    await st.set_status("a", NodeStatus.RUNNING)
    await st.set_status("a", NodeStatus.SUCCESS)
    snap = await st.status_snapshot()
    assert snap == {"a": NodeStatus.SUCCESS}


@pytest.mark.asyncio
async def test_graph_exec_state_deadline() -> None:
    past = datetime.now(timezone.utc).replace(year=2020)
    st = GraphExecState.create(graph_id=1, run_id="run", deadline_at=past)
    assert st.is_deadline_exceeded() is True

    future_st = GraphExecState.create(
        graph_id=1, run_id="run", deadline_at=datetime.now(timezone.utc).replace(year=2099)
    )
    assert future_st.is_deadline_exceeded() is False
