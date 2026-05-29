"""Graph Orchestrator 单元测试

覆盖：
- spec 校验：唯一 node id / 唯一 edge id / 边引用合法 / 唯一 start / 至少 1 end
- 拓扑：环检测 / 不可达 / 正常排序
- 执行：单节点 / 链式 / 分叉（并发）/ if_else 分支 / 错误传播
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from chameleon.engine.graph import (
    EdgeSpec,
    GraphSpec,
    Node,
    NodeContext,
    NodeSpec,
    NodeStatus,
)
from chameleon.engine.graph.engine import Orchestrator
from chameleon.engine.graph.registry import register_node_type
from chameleon.engine.graph.results import assert_acyclic

# ── 测试用节点 ───────────────────────────────────────────


class _EchoNode(Node[Any, Any]):
    type = "_echo"

    async def execute(self, ctx: NodeContext, input: Any) -> Any:
        return {"echoed": input, "node": self.id}


class _BoomNode(Node[Any, Any]):
    """永远 raise 的节点，用于错误传播测"""

    type = "_boom"

    async def execute(self, ctx: NodeContext, input: Any) -> Any:
        raise RuntimeError("boom!")


class _IfNode(Node[Any, Any]):
    type = "_if"

    async def execute(self, ctx: NodeContext, input: Any) -> Any:
        return {"value": input.get("value", 0) > 0}

    def selected_branch(self, output: Any) -> str | None:
        return "true" if output["value"] else "false"


# 因为 _if 在 executor 内部按 type=='if_else' 才走 selected_branch；
# 我们需要让 _IfNode 也走 selected_branch —— 改写 type 为 'if_else'
class _RealIfElse(_IfNode):
    type = "if_else"


register_node_type(_EchoNode)
register_node_type(_BoomNode)
# 不注册 _RealIfElse —— 它和真实 if_else 节点冲突；测试用 node_factory 注入


# ── helper ───────────────────────────────────────────────


def _ctx() -> NodeContext:
    return NodeContext(
        request_id="rid-test",
        graph_id=1,
        graph_run_id=1,
        depth=0,
        started_at=datetime.now(timezone.utc),
    )


def _factory_with_if_else(spec: NodeSpec) -> Node:
    """测试用 factory：把 'if_else' 路由到 _RealIfElse"""
    from chameleon.engine.graph.registry import _NODE_REGISTRY

    if spec.type == "if_else":
        return _RealIfElse(spec)
    cls = _NODE_REGISTRY.get(spec.type)
    assert cls is not None, f"unknown type {spec.type}"
    return cls(spec)


# ── spec 校验 ────────────────────────────────────────────


def test_spec_dup_node_id_rejected():
    with pytest.raises(ValidationError, match="重复 node id"):
        GraphSpec(
            nodes=[
                NodeSpec(id="a", type="start"),
                NodeSpec(id="a", type="end"),
            ],
            edges=[],
        )


def test_spec_dup_edge_id_rejected():
    with pytest.raises(ValidationError, match="重复 edge id"):
        GraphSpec(
            nodes=[
                NodeSpec(id="s", type="start"),
                NodeSpec(id="e", type="end"),
            ],
            edges=[
                EdgeSpec(id="x", source="s", target="e"),
                EdgeSpec(id="x", source="e", target="s"),
            ],
        )


def test_spec_edge_unknown_node_rejected():
    with pytest.raises(ValidationError, match="不存在于 nodes"):
        GraphSpec(
            nodes=[
                NodeSpec(id="s", type="start"),
                NodeSpec(id="e", type="end"),
            ],
            edges=[EdgeSpec(id="x", source="s", target="ghost")],
        )


def test_spec_must_have_exactly_one_start():
    with pytest.raises(ValidationError, match="1 个 start"):
        GraphSpec(
            nodes=[NodeSpec(id="e", type="end")],
            edges=[],
        )


def test_spec_must_have_at_least_one_end():
    with pytest.raises(ValidationError, match="至少有 1 个 end"):
        GraphSpec(
            nodes=[NodeSpec(id="s", type="start")],
            edges=[],
        )


# ── 拓扑 / 环检测 ─────────────────────────────────────────


def test_topo_acyclic_passes():
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="m", type="_echo"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="m"),
            EdgeSpec(id="2", source="m", target="e"),
        ],
    )
    assert_acyclic(spec)  # 不抛即过


def test_topo_cycle_detected():
    # s → m → e, 加 e → m 制造环
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="m", type="_echo"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="m"),
            EdgeSpec(id="2", source="m", target="e"),
            EdgeSpec(id="3", source="e", target="m"),
        ],
    )
    with pytest.raises(ValueError, match="含环"):
        assert_acyclic(spec)


# ── 执行 ─────────────────────────────────────────────────


async def test_run_single_node_chain():
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[EdgeSpec(id="1", source="s", target="e")],
    )
    executor = Orchestrator(spec)
    result = await executor.run(input={"hello": "world"}, ctx=_ctx())
    assert result.status == NodeStatus.SUCCESS
    assert result.output == {"hello": "world"}
    # 走了 start + end 两节点
    assert len(result.node_runs) == 2
    assert [r.status for r in result.node_runs] == [
        NodeStatus.SUCCESS,
        NodeStatus.SUCCESS,
    ]


async def test_run_chain_of_three():
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="m", type="_echo"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="m"),
            EdgeSpec(id="2", source="m", target="e"),
        ],
    )
    executor = Orchestrator(spec)
    result = await executor.run(input={"v": 42}, ctx=_ctx())
    assert result.status == NodeStatus.SUCCESS
    # _echo 节点会把 input 包成 {echoed: ..., node: m}
    assert result.output == {"echoed": {"v": 42}, "node": "m"}
    assert len(result.node_runs) == 3


async def test_run_error_propagation():
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="b", type="_boom"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="b"),
            EdgeSpec(id="2", source="b", target="e"),
        ],
    )
    executor = Orchestrator(spec)
    result = await executor.run(input={}, ctx=_ctx())
    assert result.status == NodeStatus.FAILED
    assert result.error is not None
    assert result.error["type"] == "RuntimeError"
    assert "boom" in result.error["message"]
    # boom 节点失败 → e 没跑
    statuses = [r.status for r in result.node_runs]
    assert NodeStatus.FAILED in statuses
    assert NodeStatus.SUCCESS in statuses  # start 跑了


async def test_run_if_else_true_branch():
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="g", type="if_else"),
            NodeSpec(id="t", type="_echo"),
            NodeSpec(id="f", type="_echo"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="g"),
            EdgeSpec(id="2", source="g", target="t", source_handle="true"),
            EdgeSpec(id="3", source="g", target="f", source_handle="false"),
            EdgeSpec(id="4", source="t", target="e"),
            EdgeSpec(id="5", source="f", target="e"),
        ],
    )
    executor = Orchestrator(spec, node_factory=_factory_with_if_else)
    result = await executor.run(input={"value": 100}, ctx=_ctx())
    assert result.status == NodeStatus.SUCCESS
    # 应走 t 分支：node_runs 含 s/g/t/e，不含 f
    node_ids = [r.node_id for r in result.node_runs]
    assert "t" in node_ids
    assert "f" not in node_ids


async def test_run_if_else_false_branch():
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="g", type="if_else"),
            NodeSpec(id="t", type="_echo"),
            NodeSpec(id="f", type="_echo"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="g"),
            EdgeSpec(id="2", source="g", target="t", source_handle="true"),
            EdgeSpec(id="3", source="g", target="f", source_handle="false"),
            EdgeSpec(id="4", source="t", target="e"),
            EdgeSpec(id="5", source="f", target="e"),
        ],
    )
    executor = Orchestrator(spec, node_factory=_factory_with_if_else)
    result = await executor.run(input={"value": -1}, ctx=_ctx())
    assert result.status == NodeStatus.SUCCESS
    node_ids = [r.node_id for r in result.node_runs]
    assert "f" in node_ids
    assert "t" not in node_ids


async def test_run_no_drain_tail_latency():
    """事件驱动主循环：图跑完即返回，无固定轮询拖尾

    回归旧 0.2s wait_for 拖尾 —— 几个瞬时节点的链应在远小于 200ms 内完成。
    """
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="m", type="_echo"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="m"),
            EdgeSpec(id="2", source="m", target="e"),
        ],
    )
    t0 = time.monotonic()
    result = await Orchestrator(spec).run(input={"v": 1}, ctx=_ctx())
    elapsed = time.monotonic() - t0
    assert result.status == NodeStatus.SUCCESS
    assert elapsed < 0.1  # 旧实现末尾会卡 ~0.2s


async def test_run_dangling_non_end_node_still_runs():
    """DAG executor 语义：非 end 的叶子节点（无 outgoing）照常执行后停止

    s 有两条出边：→ dangling（叶子，无后继）和 → e（end）。
    旧 executor.py 单路径走法会在 dangling 处报"断裂"；
    PR88b Orchestrator 是拓扑 DAG 执行器：两个分支都跑，输出取 end 节点。
    """
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="dangling", type="_echo"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="dangling"),
            EdgeSpec(id="2", source="s", target="e"),  # s 多出边
        ],
    )
    executor = Orchestrator(spec)
    result = await executor.run(input={"hi": 1}, ctx=_ctx())
    assert result.status == NodeStatus.SUCCESS
    node_ids = {r.node_id for r in result.node_runs}
    # dangling 与 end 都执行了
    assert node_ids == {"s", "dangling", "e"}
    # 输出取 end 节点（透传 graph input）
    assert result.output == {"hi": 1}


async def test_run_if_else_merge_join_runs_end():
    """if_else 两分支汇聚到 end（diamond join）—— A0 OR-join 修复回归

    选中 true 分支后 false 分支被 skip；end 入度 2，但只要 true 分支
    完成就必须执行（不能因 skip 把 end 入度打成负数而永不入队）。
    """
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="g", type="if_else"),
            NodeSpec(id="t", type="_echo"),
            NodeSpec(id="f", type="_echo"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="g"),
            EdgeSpec(id="2", source="g", target="t", source_handle="true"),
            EdgeSpec(id="3", source="g", target="f", source_handle="false"),
            EdgeSpec(id="4", source="t", target="e"),
            EdgeSpec(id="5", source="f", target="e"),
        ],
    )
    executor = Orchestrator(spec, node_factory=_factory_with_if_else)
    result = await executor.run(input={"value": 7}, ctx=_ctx())
    assert result.status == NodeStatus.SUCCESS
    node_ids = {r.node_id for r in result.node_runs}
    assert "t" in node_ids
    assert "f" not in node_ids  # 未选中分支被 skip
    assert "e" in node_ids  # 汇聚节点照常执行（OR-join）
