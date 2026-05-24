"""ParallelNode 单测（v1.1 PR A5）

覆盖：collect / merge / race join 策略、真并发（计时）、分支失败传播、
配置校验、嵌套深度守卫。
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import pytest

from chameleon.core.graph import EdgeSpec, GraphSpec, Node, NodeContext, NodeSpec
from chameleon.core.graph.nodes._subgraph import MAX_NEST_DEPTH
from chameleon.core.graph.nodes.parallel import ParallelNode
from chameleon.core.graph.registry import register_node_type

# ── 子图用节点 ───────────────────────────────────────────


class _ParConstNode(Node[Any, Any]):
    """返回 spec.data.value（固定 dict）—— 让不同 branch 产不同输出"""

    type = "_par_const"

    async def execute(self, ctx: NodeContext, input: Any) -> Any:
        return self.spec.data.get("value", {})


class _ParSleepNode(Node[Any, Any]):
    """sleep spec.data.ms 毫秒 —— 测真并发"""

    type = "_par_sleep"

    async def execute(self, ctx: NodeContext, input: Any) -> Any:
        ms = int(self.spec.data.get("ms", 50))
        await asyncio.sleep(ms / 1000)
        return {"slept_ms": ms}


class _ParBoomNode(Node[Any, Any]):
    type = "_par_boom"

    async def execute(self, ctx: NodeContext, input: Any) -> Any:
        raise RuntimeError("branch boom")


register_node_type(_ParConstNode)
register_node_type(_ParSleepNode)
register_node_type(_ParBoomNode)


def _ctx(depth: int = 0) -> NodeContext:
    return NodeContext(
        request_id="rid-par",
        graph_id=1,
        graph_run_id=1,
        depth=depth,
        started_at=datetime.now(timezone.utc),
    )


def _body(node_type: str, data: dict | None = None) -> dict:
    """start → <node> → end 子图 dict"""
    return GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(id="n", type=node_type, data=data or {}),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="n"),
            EdgeSpec(id="2", source="n", target="e"),
        ],
    ).model_dump()


# ── collect ──────────────────────────────────────────────


async def test_parallel_collect():
    node = ParallelNode(
        NodeSpec(
            id="p",
            type="parallel",
            data={
                "branches": [
                    {"key": "a", "body": _body("_par_const", {"value": {"a": 1}})},
                    {"key": "b", "body": _body("_par_const", {"value": {"b": 2}})},
                ]
            },
        )
    )
    out = await node.execute(_ctx(), {"shared": "in"})
    assert out["branches"] == {"a": {"a": 1}, "b": {"b": 2}}
    assert {r["key"] for r in out["branch_runs"]} == {"a", "b"}
    assert all(r["ok"] for r in out["branch_runs"])


# ── merge ────────────────────────────────────────────────


async def test_parallel_merge():
    node = ParallelNode(
        NodeSpec(
            id="p",
            type="parallel",
            data={
                "join_strategy": "merge",
                "branches": [
                    {"key": "a", "body": _body("_par_const", {"value": {"a": 1}})},
                    {"key": "b", "body": _body("_par_const", {"value": {"b": 2}})},
                ],
            },
        )
    )
    out = await node.execute(_ctx(), {})
    assert out["merged"] == {"a": 1, "b": 2}
    assert out["branches"]["a"] == {"a": 1}


# ── 真并发（计时）─────────────────────────────────────────


async def test_parallel_runs_concurrently():
    # 3 分支各 sleep 120ms，全并发 → 墙钟应远小于 360ms 串行
    branches = [
        {"key": f"b{i}", "body": _body("_par_sleep", {"ms": 120})}
        for i in range(3)
    ]
    node = ParallelNode(
        NodeSpec(id="p", type="parallel", data={"branches": branches})
    )
    t0 = time.monotonic()
    out = await node.execute(_ctx(), {})
    elapsed = time.monotonic() - t0
    assert len(out["branches"]) == 3
    assert elapsed < 0.30  # 并发；串行会 ~0.36s


async def test_parallel_concurrency_limit_serializes():
    # concurrency=1 → 退化串行：2 分支各 80ms ≈ 160ms
    branches = [
        {"key": f"b{i}", "body": _body("_par_sleep", {"ms": 80})}
        for i in range(2)
    ]
    node = ParallelNode(
        NodeSpec(
            id="p",
            type="parallel",
            data={"branches": branches, "concurrency": 1},
        )
    )
    t0 = time.monotonic()
    await node.execute(_ctx(), {})
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.15  # 串行下界


# ── race ─────────────────────────────────────────────────


async def test_parallel_race_fastest_wins():
    node = ParallelNode(
        NodeSpec(
            id="p",
            type="parallel",
            data={
                "join_strategy": "race",
                "branches": [
                    {"key": "slow", "body": _body("_par_sleep", {"ms": 300})},
                    {"key": "fast", "body": _body("_par_sleep", {"ms": 20})},
                ],
            },
        )
    )
    t0 = time.monotonic()
    out = await node.execute(_ctx(), {})
    elapsed = time.monotonic() - t0
    assert out["winner"] == "fast"
    assert out["output"] == {"slept_ms": 20}
    assert elapsed < 0.20  # 不等 slow 跑完


async def test_parallel_race_skips_failed_branch():
    """最快的分支失败 → 取下一个成功的为 winner"""
    node = ParallelNode(
        NodeSpec(
            id="p",
            type="parallel",
            data={
                "join_strategy": "race",
                "branches": [
                    {"key": "boom", "body": _body("_par_boom")},
                    {"key": "ok", "body": _body("_par_sleep", {"ms": 60})},
                ],
            },
        )
    )
    out = await node.execute(_ctx(), {})
    assert out["winner"] == "ok"


# ── 失败传播 ──────────────────────────────────────────────


async def test_parallel_collect_branch_failure_propagates():
    node = ParallelNode(
        NodeSpec(
            id="p",
            type="parallel",
            data={
                "branches": [
                    {"key": "ok", "body": _body("_par_const", {"value": {"x": 1}})},
                    {"key": "bad", "body": _body("_par_boom")},
                ]
            },
        )
    )
    with pytest.raises(RuntimeError, match=r"分支\[bad\]失败"):
        await node.execute(_ctx(), {})


# ── 配置校验 + 深度守卫 ───────────────────────────────────


def test_parallel_requires_two_branches():
    with pytest.raises(ValueError, match="至少 2 条"):
        ParallelNode(
            NodeSpec(
                id="p",
                type="parallel",
                data={"branches": [{"key": "a", "body": _body("_par_const")}]},
            )
        )


def test_parallel_duplicate_branch_key():
    with pytest.raises(ValueError, match="key 重复"):
        ParallelNode(
            NodeSpec(
                id="p",
                type="parallel",
                data={
                    "branches": [
                        {"key": "a", "body": _body("_par_const")},
                        {"key": "a", "body": _body("_par_const")},
                    ]
                },
            )
        )


def test_parallel_bad_join_strategy():
    with pytest.raises(ValueError, match="join_strategy"):
        ParallelNode(
            NodeSpec(
                id="p",
                type="parallel",
                data={
                    "join_strategy": "nonsense",
                    "branches": [
                        {"key": "a", "body": _body("_par_const")},
                        {"key": "b", "body": _body("_par_const")},
                    ],
                },
            )
        )


async def test_parallel_depth_guard():
    node = ParallelNode(
        NodeSpec(
            id="p",
            type="parallel",
            data={
                "branches": [
                    {"key": "a", "body": _body("_par_const")},
                    {"key": "b", "body": _body("_par_const")},
                ]
            },
        )
    )
    with pytest.raises(ValueError, match="嵌套过深"):
        await node.execute(_ctx(depth=MAX_NEST_DEPTH), {})
