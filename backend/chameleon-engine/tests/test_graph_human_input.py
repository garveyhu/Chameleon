"""HumanInLoopNode + Orchestrator 暂停/恢复 引擎核心单测（v1.1 PR A6）

覆盖：节点抛 HumanInputRequired / 整图 PAUSED + pending + node_outputs 快照 /
seed_outputs 重放跳过执行 / resume 回填后跑完 / 多断点逐次恢复。
（持久化 ORM + service + APScheduler 的 e2e 待 DB 环境。）
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from chameleon.engine.graph import EdgeSpec, GraphSpec, Node, NodeContext, NodeSpec
from chameleon.engine.graph.engine import Orchestrator
from chameleon.engine.graph.node_base import HumanInputRequired, NodeStatus
from chameleon.engine.graph.nodes.human_input import HumanInLoopNode
from chameleon.engine.graph.registry import register_node_type


class _HilEchoNode(Node[Any, Any]):
    type = "_hil_echo"

    async def execute(self, ctx: NodeContext, input: Any) -> Any:
        return {"echoed": input}


class _HilBoomNode(Node[Any, Any]):
    type = "_hil_boom"

    async def execute(self, ctx: NodeContext, input: Any) -> Any:
        raise RuntimeError("should not run when seeded")


register_node_type(_HilEchoNode)
register_node_type(_HilBoomNode)


def _ctx() -> NodeContext:
    return NodeContext(
        request_id="rid-hil",
        graph_id=1,
        graph_run_id=1,
        depth=0,
        started_at=datetime.now(timezone.utc),
    )


# ── 节点本身 ──────────────────────────────────────────────


async def test_human_node_always_raises():
    node = HumanInLoopNode(
        NodeSpec(
            id="h",
            type="human_input",
            data={"prompt": "审核", "schema": {"type": "object"}},
        )
    )
    with pytest.raises(HumanInputRequired) as ei:
        await node.execute(_ctx(), {"x": 1})
    assert ei.value.node_id == "h"
    assert ei.value.prompt == "审核"
    assert ei.value.node_input == {"x": 1}


def test_human_node_validate_timeout():
    with pytest.raises(ValueError, match="timeout_seconds"):
        HumanInLoopNode(
            NodeSpec(id="h", type="human_input", data={"timeout_seconds": 0})
        )


# ── 暂停 ──────────────────────────────────────────────────


def _hil_spec() -> GraphSpec:
    """start → human → echo → end"""
    return GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="h", type="human_input", data={"prompt": "p"}),
            NodeSpec(id="m", type="_hil_echo"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="h"),
            EdgeSpec(id="2", source="h", target="m"),
            EdgeSpec(id="3", source="m", target="e"),
        ],
    )


async def test_run_pauses_at_human_node():
    result = await Orchestrator(_hil_spec()).run(input={"q": "hi"}, ctx=_ctx())
    assert result.status == NodeStatus.PAUSED
    assert result.pending is not None
    assert result.pending["node_id"] == "h"
    assert result.pending["prompt"] == "p"
    assert result.pending["node_input"] == {"q": "hi"}
    # start 已完成，快照里有它的输出；human/echo/end 未跑
    assert "s" in result.node_outputs
    assert "m" not in result.node_outputs
    # 下游 echo/end 没执行
    ran = {r.node_id for r in result.node_runs}
    assert "m" not in ran and "e" not in ran


# ── resume：seed 重放跳过执行 + 回填跑完 ────────────────────


async def test_seed_replay_skips_execution():
    """seed 命中的节点直接重放输出，不调 execute（boom 节点也不炸）"""
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="b", type="_hil_boom"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="b"),
            EdgeSpec(id="2", source="b", target="e"),
        ],
    )
    result = await Orchestrator(spec).run(
        input={"q": 1},
        ctx=_ctx(),
        seed_outputs={"b": {"seeded": True}},
    )
    assert result.status == NodeStatus.SUCCESS
    # end 拿到被重放的 boom 输出
    assert result.output == {"seeded": True}


async def test_resume_after_human_fill_completes():
    spec = _hil_spec()
    # 第一次跑 → 暂停
    r1 = await Orchestrator(spec).run(input={"q": "hi"}, ctx=_ctx())
    assert r1.status == NodeStatus.PAUSED

    # 回填：seed = 已完成快照 + human 节点的人工值
    seed = dict(r1.node_outputs)
    seed["h"] = {"approved": True, "note": "ok"}
    r2 = await Orchestrator(spec).run(
        input={"q": "hi"}, ctx=_ctx(), seed_outputs=seed
    )
    assert r2.status == NodeStatus.SUCCESS
    # echo 收到 human 回填值 → end 输出 {"echoed": human_value}
    assert r2.output == {"echoed": {"approved": True, "note": "ok"}}
    # 恢复后 human 节点按 success 记账（重放）
    statuses = {r.node_id: r.status for r in r2.node_runs}
    assert statuses["h"] == NodeStatus.SUCCESS
    assert statuses["m"] == NodeStatus.SUCCESS


async def test_two_human_nodes_resume_twice():
    """两个串行断点：逐次回填恢复"""
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="h1", type="human_input"),
            NodeSpec(id="h2", type="human_input"),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="h1"),
            EdgeSpec(id="2", source="h1", target="h2"),
            EdgeSpec(id="3", source="h2", target="e"),
        ],
    )
    # 第一次：停在 h1
    r1 = await Orchestrator(spec).run(input={"q": 1}, ctx=_ctx())
    assert r1.status == NodeStatus.PAUSED
    assert r1.pending["node_id"] == "h1"

    # 回填 h1 → 停在 h2
    seed = dict(r1.node_outputs)
    seed["h1"] = {"a": 1}
    r2 = await Orchestrator(spec).run(input={"q": 1}, ctx=_ctx(), seed_outputs=seed)
    assert r2.status == NodeStatus.PAUSED
    assert r2.pending["node_id"] == "h2"
    # h2 拿到 h1 的回填值作 input
    assert r2.pending["node_input"] == {"a": 1}

    # 回填 h2 → 跑完
    seed2 = dict(r2.node_outputs)
    seed2["h2"] = {"b": 2}
    r3 = await Orchestrator(spec).run(input={"q": 1}, ctx=_ctx(), seed_outputs=seed2)
    assert r3.status == NodeStatus.SUCCESS
    assert r3.output == {"b": 2}
