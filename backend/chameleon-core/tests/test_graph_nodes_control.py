"""IfElseNode / ToolNode 单元测试（P18.1 PR #19）"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from chameleon.core.graph import (
    EdgeSpec,
    GraphSpec,
    NodeContext,
    NodeSpec,
    NodeStatus,
)
from chameleon.core.graph.engine import Orchestrator
from chameleon.core.graph.nodes.if_else import IfElseNode
from chameleon.core.graph.nodes.tool import ToolNode, register_tool


def _ctx() -> NodeContext:
    return NodeContext(
        request_id="rid",
        graph_id=1,
        graph_run_id=1,
        depth=0,
        started_at=datetime.now(timezone.utc),
    )


# ── IfElseNode 表达式校验 ────────────────────────────────


def test_if_else_requires_condition():
    with pytest.raises(ValueError, match="condition 必填"):
        IfElseNode(NodeSpec(id="g", type="if_else", data={}))


def test_if_else_unknown_op_rejected():
    with pytest.raises(ValueError, match="未知 op"):
        IfElseNode(
            NodeSpec(
                id="g",
                type="if_else",
                data={"condition": {"op": "frobnicate", "left": 1, "right": 2}},
            )
        )


def test_if_else_excessive_depth_rejected():
    # 构造 18 层嵌套
    cond = {"const": True}
    for _ in range(20):
        cond = {"op": "not", "value": cond}
    with pytest.raises(ValueError, match="嵌套层级"):
        IfElseNode(
            NodeSpec(id="g", type="if_else", data={"condition": cond})
        )


# ── IfElseNode 求值 ─────────────────────────────────────


async def test_if_else_var_comparison_true():
    node = IfElseNode(
        NodeSpec(
            id="g",
            type="if_else",
            data={
                "condition": {
                    "op": ">",
                    "left": {"var": "score"},
                    "right": 0.5,
                }
            },
        )
    )
    out = await node.execute(_ctx(), {"score": 0.8})
    assert out["branch"] == "true"
    assert out["value"] is True


async def test_if_else_var_missing_default():
    node = IfElseNode(
        NodeSpec(
            id="g",
            type="if_else",
            data={
                "condition": {
                    "op": "==",
                    "left": {"var": "missing", "default": "fallback"},
                    "right": "fallback",
                }
            },
        )
    )
    out = await node.execute(_ctx(), {})
    assert out["branch"] == "true"


async def test_if_else_nested_dot_var():
    node = IfElseNode(
        NodeSpec(
            id="g",
            type="if_else",
            data={
                "condition": {
                    "op": "==",
                    "left": {"var": "user.role"},
                    "right": "admin",
                }
            },
        )
    )
    out = await node.execute(_ctx(), {"user": {"role": "admin"}})
    assert out["branch"] == "true"


async def test_if_else_and_or():
    node = IfElseNode(
        NodeSpec(
            id="g",
            type="if_else",
            data={
                "condition": {
                    "op": "and",
                    "left": {
                        "op": ">",
                        "left": {"var": "score"},
                        "right": 0.5,
                    },
                    "right": {
                        "op": "==",
                        "left": {"var": "status"},
                        "right": "ok",
                    },
                }
            },
        )
    )
    out = await node.execute(_ctx(), {"score": 0.9, "status": "ok"})
    assert out["branch"] == "true"
    out = await node.execute(_ctx(), {"score": 0.9, "status": "bad"})
    assert out["branch"] == "false"


async def test_if_else_type_mismatch_raises():
    node = IfElseNode(
        NodeSpec(
            id="g",
            type="if_else",
            data={"condition": {"op": ">", "left": {"var": "x"}, "right": 1}},
        )
    )
    with pytest.raises(ValueError, match="不能比较"):
        await node.execute(_ctx(), {"x": "foo"})


# ── Tool stub ────────────────────────────────────────────


def test_tool_node_requires_tool_key():
    with pytest.raises(ValueError, match="tool_key 必填"):
        ToolNode(NodeSpec(id="t", type="tool", data={}))


async def test_tool_node_unknown_key_raises():
    node = ToolNode(
        NodeSpec(id="t", type="tool", data={"tool_key": "no-such-tool"})
    )
    with pytest.raises(RuntimeError, match="未注册"):
        await node.execute(_ctx(), {})


async def test_tool_node_with_registered_tool():
    """P18.2 后 register_tool 注入：ToolNode 能跑通"""

    class _PingTool:
        tool_key = "ping"

        async def run(self, args, ctx):
            return {"ok": True, "received": args}

    register_tool(_PingTool)
    node = ToolNode(
        NodeSpec(
            id="t",
            type="tool",
            data={"tool_key": "ping", "args": {"target": "1.1.1.1"}},
        )
    )
    out = await node.execute(_ctx(), {"extra": "z"})
    assert out["tool_key"] == "ping"
    # input 与 args 合并；args 优先
    assert out["result"]["received"] == {
        "extra": "z",
        "target": "1.1.1.1",
    }


# ── 端到端：if_else 走 true 分支 → end ───────────────────


async def test_end_to_end_if_else_routes_correctly():
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(
                id="g",
                type="if_else",
                data={
                    "condition": {
                        "op": ">",
                        "left": {"var": "score"},
                        "right": 0.5,
                    }
                },
            ),
            NodeSpec(id="good", type="noop"),
            NodeSpec(id="bad", type="noop"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="g"),
            EdgeSpec(id="2", source="g", target="good", source_handle="true"),
            EdgeSpec(id="3", source="g", target="bad", source_handle="false"),
            EdgeSpec(id="4", source="good", target="e"),
            EdgeSpec(id="5", source="bad", target="e"),
        ],
    )
    executor = Orchestrator(spec)

    # 高分走 good
    result = await executor.run(input={"score": 0.9}, ctx=_ctx())
    assert result.status == NodeStatus.SUCCESS
    node_ids = [r.node_id for r in result.node_runs]
    assert "good" in node_ids
    assert "bad" not in node_ids

    # 低分走 bad
    result = await executor.run(input={"score": 0.1}, ctx=_ctx())
    node_ids = [r.node_id for r in result.node_runs]
    assert "bad" in node_ids
    assert "good" not in node_ids
