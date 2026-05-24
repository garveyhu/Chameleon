"""Observation 树 cost / token 递归聚合（P23.C2）

trace tree 上每条 call_log 只记自己那一层的 cost / token；要展示"这个 observation
连同它所有子孙一共花了多少"需要自底向上累加。

本模块是**纯函数聚合**：不碰 DB、不依赖 system 层 schema —— 输入一批 CallLog 行
（同一棵或多棵树的节点集合），按 parent_id 链路在内存里算出每个 request_id 的
subtree rollup（含自身）。调用方（admin trace service）拿 rollup 映射回各自的
展示 schema。

cost 语义：subtree 内没有任何节点有 cost（model_code/价目缺失）时 rollup cost 为
None —— 让前端显示"—"而不是误导性的 $0.00。token 则按 0 累加。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from chameleon.core.models import CallLog


@dataclass(slots=True)
class ObservationRollup:
    """单个 observation 连同其所有后代的累加值（含自身）"""

    # subtree 内全无 cost 时为 None；否则为所有有 cost 节点之和
    cost_usd: Decimal | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    # 含自身的 subtree 节点数（调试 / 展示用）
    node_count: int


def aggregate_rollups(logs: Iterable[CallLog]) -> dict[str, ObservationRollup]:
    """对一批 call_log 算 subtree rollup，返回 {request_id: ObservationRollup}

    只在传入集合内部按 parent_id 连边；指向集合外的 parent_id 视为断链（该节点
    自成一个 subtree 根）。对环做防御（visited 标记），不会无限递归。

    Args:
        logs: 同一棵或多棵 observation 树的 call_log 行（顺序无关）

    Returns:
        每个 request_id 对应其 subtree（含自身）的累加值
    """
    by_rid: dict[str, CallLog] = {log.request_id: log for log in logs}
    # parent_id -> [child request_id]
    children: dict[str, list[str]] = {}
    for rid, log in by_rid.items():
        pid = log.parent_id
        if pid is not None and pid in by_rid:
            children.setdefault(pid, []).append(rid)

    rollups: dict[str, ObservationRollup] = {}

    def compute(rid: str, visited: set[str]) -> ObservationRollup:
        cached = rollups.get(rid)
        if cached is not None:
            return cached
        if rid in visited:
            # 环：把当前节点当叶子处理，避免无限递归
            return _self_rollup(by_rid[rid])
        visited.add(rid)

        log = by_rid[rid]
        acc = _self_rollup(log)
        for child_rid in children.get(rid, ()):
            child = compute(child_rid, visited)
            acc = _merge(acc, child)

        visited.discard(rid)
        rollups[rid] = acc
        return acc

    for rid in by_rid:
        compute(rid, set())

    return rollups


def _self_rollup(log: CallLog) -> ObservationRollup:
    """单节点自身（不含子）的 rollup"""
    return ObservationRollup(
        cost_usd=_as_decimal(log.cost_usd),
        prompt_tokens=log.prompt_tokens or 0,
        completion_tokens=log.completion_tokens or 0,
        total_tokens=log.total_tokens or 0,
        node_count=1,
    )


def _merge(a: ObservationRollup, b: ObservationRollup) -> ObservationRollup:
    """合并两个 rollup（父累加子）—— cost 的 None 语义：两边都 None 才 None"""
    if a.cost_usd is None:
        cost = b.cost_usd
    elif b.cost_usd is None:
        cost = a.cost_usd
    else:
        cost = a.cost_usd + b.cost_usd
    return ObservationRollup(
        cost_usd=cost,
        prompt_tokens=a.prompt_tokens + b.prompt_tokens,
        completion_tokens=a.completion_tokens + b.completion_tokens,
        total_tokens=a.total_tokens + b.total_tokens,
        node_count=a.node_count + b.node_count,
    )


def _as_decimal(value: Decimal | float | None) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))
