"""图执行结果 DTO + 拓扑校验

- NodeRunResult：单节点执行记录（落 graph_node_runs 表）
- RunResult：整张图执行记录（落 graph_runs 表的 result 字段 + node_runs 子集）
- assert_acyclic：spec 校验入口；Orchestrator 启动时调

不放 ORM；service 层把这些 Pydantic DTO 转 ORM 写库。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from chameleon.core.graph.node_base import NodeStatus
from chameleon.core.graph.types import GraphSpec

# ── DTO ──────────────────────────────────────────────────


class NodeRunResult(BaseModel):
    """单节点执行结果"""

    node_id: str
    node_type: str
    status: NodeStatus
    input: Any = None
    output: Any = None
    error: dict[str, Any] | None = None
    started_at: datetime
    finished_at: datetime
    duration_ms: int


class RunResult(BaseModel):
    """整张图的执行结果"""

    status: NodeStatus  # success / failed / paused
    input: Any
    output: Any = None
    error: dict[str, Any] | None = None
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    node_runs: list[NodeRunResult] = Field(default_factory=list)
    # A6 暂停：等待人工回填的节点信息（status=PAUSED 时非空）
    pending: dict[str, Any] | None = None
    # A6 暂停：已完成节点输出快照（resume 时作为 seed_outputs 重放，跳过重跑）
    node_outputs: dict[str, Any] = Field(default_factory=dict)


# ── 拓扑校验 ─────────────────────────────────────────────


def _topological_sort(spec: GraphSpec) -> list[str]:
    """Kahn 拓扑排序；有环则 raise ValueError

    返回 node_id 拓扑顺序列表。
    """
    in_degree: dict[str, int] = defaultdict(int)
    adj: dict[str, list[str]] = defaultdict(list)
    for n in spec.nodes:
        in_degree[n.id] = in_degree.get(n.id, 0)
    for e in spec.edges:
        adj[e.source].append(e.target)
        in_degree[e.target] += 1

    queue: list[str] = [nid for nid, deg in in_degree.items() if deg == 0]
    order: list[str] = []
    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for nxt in adj[nid]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)
    if len(order) != len(spec.nodes):
        unreachable = set(n.id for n in spec.nodes) - set(order)
        raise ValueError(f"图含环 / 不可达节点：{sorted(unreachable)}")
    return order


def assert_acyclic(spec: GraphSpec) -> None:
    """显式调用：spec 是否无环"""
    _topological_sort(spec)


# ── 小工具 ─────────────────────────────────────────────


def duration_ms(t0: datetime, t1: datetime) -> int:
    return int((t1 - t0).total_seconds() * 1000)
