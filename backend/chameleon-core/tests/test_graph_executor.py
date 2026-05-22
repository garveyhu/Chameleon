"""GraphExecutor 单元测试（P18.1 PR #17）

覆盖：
- spec 校验：唯一 node id / 唯一 edge id / 边引用合法 / 唯一 start / 至少 1 end
- 拓扑：环检测 / 不可达 / 正常排序
- 执行：单节点 / 链式 / 分叉（取首边）/ if_else 分支 / 错误传播
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from chameleon.core.graph import (
    EdgeSpec,
    GraphExecutor,
    GraphSpec,
    Node,
    NodeContext,
    NodeSpec,
    NodeStatus,
)
from chameleon.core.graph.executor import (
    assert_acyclic,
    register_node_type,
)


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
    from chameleon.core.graph.executor import _NODE_REGISTRY

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
    executor = GraphExecutor(spec)
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
    executor = GraphExecutor(spec)
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
    executor = GraphExecutor(spec)
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
    executor = GraphExecutor(spec, node_factory=_factory_with_if_else)
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
    executor = GraphExecutor(spec, node_factory=_factory_with_if_else)
    result = await executor.run(input={"value": -1}, ctx=_ctx())
    assert result.status == NodeStatus.SUCCESS
    node_ids = [r.node_id for r in result.node_runs]
    assert "f" in node_ids
    assert "t" not in node_ids


async def test_run_no_outgoing_non_end_fails():
    """节点既不是 end，又没有 outgoing 边 → executor 报错"""
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="dangling", type="_echo"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="dangling"),
            # dangling 没有 outgoing；e 没有 incoming → 但 e 可达性靠 incoming，不强制
            EdgeSpec(id="2", source="dangling", target="e"),
        ],
    )
    # 这个其实是合法的：dangling → e。换成真的 dangling：
    spec2 = GraphSpec(
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
    # 因为 s 有两条 outgoing，executor 选第一条（dangling）；dangling 没有出边 → 报错
    executor = GraphExecutor(spec2)
    result = await executor.run(input={}, ctx=_ctx())
    assert result.status == NodeStatus.FAILED
    assert result.error is not None
    assert "断裂" in result.error["message"]
