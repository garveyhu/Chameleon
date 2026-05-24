"""P23.C2: observation 树 cost / token 递归聚合

aggregate_rollups 是纯函数（不碰 DB），这里用内存 CallLog 对象直接验证：
- subtree cost / token 自底向上累加（含自身）
- 全无 cost 的 subtree → rollup cost = None（非 0）
- 断链 / 环防御
"""

from __future__ import annotations

from decimal import Decimal

from chameleon.core.models import CallLog
from chameleon.core.observe import aggregate_rollups


def _log(rid: str, parent: str | None, *, cost=None, pt=0, ct=0, tt=0) -> CallLog:
    return CallLog(
        request_id=rid,
        parent_id=parent,
        app_id="app",
        agent_key="a",
        success=True,
        code=200,
        duration_ms=1,
        cost_usd=Decimal(str(cost)) if cost is not None else None,
        prompt_tokens=pt or None,
        completion_tokens=ct or None,
        total_tokens=tt or None,
    )


def test_rollup_sums_subtree():
    # root ─┬─ a ─── gen (cost 0.002, 130 tok)
    #       └─ b (cost 0.001, 10 tok)
    logs = [
        _log("root", None, cost=None),
        _log("a", "root", cost=None),
        _log("gen", "a", cost=0.002, pt=50, ct=80, tt=130),
        _log("b", "root", cost=0.001, pt=4, ct=6, tt=10),
    ]
    r = aggregate_rollups(logs)

    # 叶子 = 自身
    assert r["gen"].cost_usd == Decimal("0.002")
    assert r["gen"].total_tokens == 130
    # a = a(0) + gen
    assert r["a"].cost_usd == Decimal("0.002")
    assert r["a"].total_tokens == 130
    assert r["a"].node_count == 2
    # root = root + a-subtree + b
    assert r["root"].cost_usd == Decimal("0.003")
    assert r["root"].prompt_tokens == 54
    assert r["root"].completion_tokens == 86
    assert r["root"].total_tokens == 140
    assert r["root"].node_count == 4


def test_rollup_all_none_cost_stays_none():
    logs = [
        _log("root", None),
        _log("c", "root", pt=1, ct=2, tt=3),
    ]
    r = aggregate_rollups(logs)
    assert r["root"].cost_usd is None  # 不是 0
    assert r["root"].total_tokens == 3


def test_rollup_broken_parent_link():
    """parent_id 指向集合外 → 该节点自成子树根，不报错"""
    logs = [_log("orphan", "missing-parent", cost=0.5, tt=9)]
    r = aggregate_rollups(logs)
    assert r["orphan"].cost_usd == Decimal("0.5")
    assert r["orphan"].total_tokens == 9
    assert r["orphan"].node_count == 1


def test_rollup_cycle_defensive():
    """环（理论上不该出现）不应无限递归"""
    logs = [
        _log("x", "y", cost=1, tt=1),
        _log("y", "x", cost=1, tt=1),
    ]
    r = aggregate_rollups(logs)
    # 不死循环、每个 key 都有结果即通过
    assert set(r.keys()) == {"x", "y"}
