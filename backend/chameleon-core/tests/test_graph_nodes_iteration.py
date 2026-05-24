"""IterationNode 单测（v1.1 PR A4）

覆盖：基本 map / items_path / item_input_key / early_stop / 并行保序 /
max_iterations 上限 / 子图失败传播 / 嵌套深度守卫 / 配置校验。

body 子图用内置 start/end（passthrough）或自定义 _iter_inc 节点。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from chameleon.core.graph import EdgeSpec, GraphSpec, Node, NodeContext, NodeSpec
from chameleon.core.graph.nodes.iteration import (
    MAX_NEST_DEPTH,
    IterationNode,
)
from chameleon.core.graph.registry import register_node_type

# ── 子图用自定义节点：n += 1 ─────────────────────────────


class _IterIncNode(Node[Any, Any]):
    type = "_iter_inc"

    async def execute(self, ctx: NodeContext, input: Any) -> Any:
        n = input.get("n", 0) if isinstance(input, dict) else 0
        return {"n": n + 1}


register_node_type(_IterIncNode)


def _ctx(depth: int = 0) -> NodeContext:
    return NodeContext(
        request_id="rid-iter",
        graph_id=1,
        graph_run_id=1,
        depth=depth,
        started_at=datetime.now(timezone.utc),
    )


def _passthrough_body() -> dict:
    """start → end：子图输出 = item 本身"""
    return GraphSpec(
        nodes=[NodeSpec(id="s", type="start"), NodeSpec(id="e", type="end")],
        edges=[EdgeSpec(id="1", source="s", target="e")],
    ).model_dump()


def _inc_body() -> dict:
    """start → inc → end：子图输出 = {n: item.n + 1}"""
    return GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="inc", type="_iter_inc"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="inc"),
            EdgeSpec(id="2", source="inc", target="e"),
        ],
    ).model_dump()


# ── 基本 map ──────────────────────────────────────────────


async def test_iteration_basic_map_passthrough():
    node = IterationNode(
        NodeSpec(id="it", type="iteration", data={"body": _passthrough_body()})
    )
    out = await node.execute(_ctx(), [{"a": 1}, {"a": 2}, {"a": 3}])
    assert out["count"] == 3
    assert out["items"] == [{"a": 1}, {"a": 2}, {"a": 3}]
    assert out["stopped_early"] is False
    assert out["stopped_at"] is None


async def test_iteration_runs_subgraph_node():
    node = IterationNode(
        NodeSpec(id="it", type="iteration", data={"body": _inc_body()})
    )
    out = await node.execute(_ctx(), [{"n": 0}, {"n": 10}])
    assert out["items"] == [{"n": 1}, {"n": 11}]


async def test_iteration_items_path():
    node = IterationNode(
        NodeSpec(
            id="it",
            type="iteration",
            data={"body": _passthrough_body(), "items_path": "urls"},
        )
    )
    out = await node.execute(_ctx(), {"urls": ["a", "b"], "other": 1})
    assert out["items"] == ["a", "b"]


async def test_iteration_item_input_key_wraps():
    node = IterationNode(
        NodeSpec(
            id="it",
            type="iteration",
            data={"body": _inc_body(), "item_input_key": "n"},
        )
    )
    # item 是裸数字，item_input_key 包成 {n: item} 喂子图
    out = await node.execute(_ctx(), [0, 5])
    assert out["items"] == [{"n": 1}, {"n": 6}]


# ── early_stop ────────────────────────────────────────────


async def test_iteration_early_stop():
    node = IterationNode(
        NodeSpec(
            id="it",
            type="iteration",
            data={
                "body": _inc_body(),
                "early_stop": {
                    "op": ">=",
                    "left": {"var": "n"},
                    "right": {"const": 2},
                },
            },
        )
    )
    # item0 → {n:1}（不停），item1 → {n:2}（停）
    out = await node.execute(_ctx(), [{"n": 0}, {"n": 1}, {"n": 100}])
    assert out["count"] == 2
    assert out["items"] == [{"n": 1}, {"n": 2}]
    assert out["stopped_early"] is True
    assert out["stopped_at"] == 1


# ── 并行保序 ──────────────────────────────────────────────


async def test_iteration_parallel_preserves_order():
    node = IterationNode(
        NodeSpec(
            id="it",
            type="iteration",
            data={"body": _inc_body(), "concurrency": 4},
        )
    )
    out = await node.execute(_ctx(), [{"n": i} for i in range(6)])
    assert out["items"] == [{"n": i + 1} for i in range(6)]
    assert out["count"] == 6


# ── max_iterations 上限 ───────────────────────────────────


async def test_iteration_max_iterations_truncates():
    node = IterationNode(
        NodeSpec(
            id="it",
            type="iteration",
            data={"body": _passthrough_body(), "max_iterations": 2},
        )
    )
    out = await node.execute(_ctx(), [1, 2, 3, 4, 5])
    assert out["count"] == 2
    assert out["items"] == [1, 2]


# ── 子图失败传播 ──────────────────────────────────────────


class _IterBoomNode(Node[Any, Any]):
    type = "_iter_boom"

    async def execute(self, ctx: NodeContext, input: Any) -> Any:
        raise RuntimeError("sub boom")


register_node_type(_IterBoomNode)


async def test_iteration_subgraph_failure_propagates():
    body = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="b", type="_iter_boom"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="b"),
            EdgeSpec(id="2", source="b", target="e"),
        ],
    ).model_dump()
    node = IterationNode(NodeSpec(id="it", type="iteration", data={"body": body}))
    with pytest.raises(RuntimeError, match=r"item\[0\] 子图失败"):
        await node.execute(_ctx(), [{"x": 1}])


# ── 嵌套深度守卫 ──────────────────────────────────────────


async def test_iteration_depth_guard():
    node = IterationNode(
        NodeSpec(id="it", type="iteration", data={"body": _passthrough_body()})
    )
    with pytest.raises(ValueError, match="嵌套过深"):
        await node.execute(_ctx(depth=MAX_NEST_DEPTH), [1, 2])


# ── 配置校验 ──────────────────────────────────────────────


def test_iteration_requires_body():
    with pytest.raises(ValueError, match="body 必填"):
        IterationNode(NodeSpec(id="it", type="iteration", data={}))


def test_iteration_invalid_body():
    with pytest.raises(ValueError, match="非法子图"):
        IterationNode(
            NodeSpec(
                id="it",
                type="iteration",
                data={"body": {"nodes": [], "edges": []}},  # 无 start/end
            )
        )


def test_iteration_concurrency_cap():
    with pytest.raises(ValueError, match="concurrency"):
        IterationNode(
            NodeSpec(
                id="it",
                type="iteration",
                data={"body": _passthrough_body(), "concurrency": 999},
            )
        )


async def test_iteration_non_list_input_errors():
    node = IterationNode(
        NodeSpec(id="it", type="iteration", data={"body": _passthrough_body()})
    )
    with pytest.raises(ValueError, match="需要 list 输入"):
        await node.execute(_ctx(), {"not": "a list"})
