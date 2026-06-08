"""durable Slice1 —— memoization 重放底座（免迁移，复用 AgentMemory）。

验：① 同一 run 重放时 ctx.complete 返 journal 记录值、不重调模型（省钱/不重复副作用）；
② durable 默认关时不记录、每次真调；③ 重放 method 不匹配 → 报错（确定性契约红线）；
④ journal 保留键不泄漏进作者 ctx.memory.all() 视图。
"""

from __future__ import annotations

import pytest

from chameleon.agentkit import AgentRun
from chameleon.agentkit.testing import FakeTransport


def _run(t: FakeTransport, *, durable: bool = False, run_id: str | None = None) -> AgentRun:
    return AgentRun(
        transport=t, agent_key="a", query="q", messages=[], history=[],
        session_id=None, config={}, durable=durable, run_id=run_id,
    )


@pytest.mark.asyncio
async def test_durable_memoize_replay_skips_model_call():
    t = FakeTransport(replies=["第一次", "第二次", "不应出现"])

    # 首跑：记录 journal，模型真调 2 次
    r1 = _run(t, durable=True, run_id="run-1")
    a1 = await r1.complete(user="x")
    a2 = await r1.complete(user="y")
    assert (a1, a2) == ("第一次", "第二次")
    n_after_record = len(t.invocations)
    assert n_after_record == 2

    # journal 保留键不泄漏进作者 memory 视图
    assert await r1.memory.all() == {}

    # 重放：同 transport（共享 memory + 同 run_id）新 AgentRun → 返记录值、模型零再调
    r2 = _run(t, durable=True, run_id="run-1")
    b1 = await r2.complete(user="x")
    b2 = await r2.complete(user="y")
    assert (b1, b2) == ("第一次", "第二次")
    assert len(t.invocations) == n_after_record  # +0：重放未触发任何模型调用


@pytest.mark.asyncio
async def test_durable_disabled_means_no_journal():
    t = FakeTransport(replies=["A", "B"])
    r = _run(t)  # durable 默认关
    assert await r.complete(user="x") == "A"
    assert await r.complete(user="x") == "B"  # 每次真调（非 memoize）
    assert len(t.invocations) == 2
    assert await r.memory.all() == {}


@pytest.mark.asyncio
async def test_durable_replay_method_mismatch_raises():
    """确定性契约：journal 记录的 method 与当前 call 不符（控制流非确定性致序列错位）→ 报错。"""
    t = FakeTransport(replies=["x"])
    await t.memory_set("__chm_journal__run-1__0__", {"method": "kb_search", "fp": "z", "output": "stale"})
    r = _run(t, durable=True, run_id="run-1")
    with pytest.raises(RuntimeError, match="与记录不符"):
        await r.complete(user="x")


@pytest.mark.asyncio
async def test_durable_fingerprint_catches_same_method_reorder():
    """评审 #1：两次 complete 因控制流非确定性换序，method 都是 'complete'——仅比 method 挡不住，
    入参指纹不同即报错（否则 idx0 静默返了属于另一调用的值）。"""
    t = FakeTransport(replies=["原本是问 A 的答案"])
    # 首跑只记了 idx0 = complete(user='A')
    r1 = _run(t, durable=True, run_id="run-1")
    await r1.complete(user="A")
    # 重放时 idx0 却来了个 complete(user='B')（控制流换序）→ 指纹不符 → 报错而非静默返 A 的答案
    r2 = _run(t, durable=True, run_id="run-1")
    with pytest.raises(RuntimeError, match="与记录不符"):
        await r2.complete(user="B")


@pytest.mark.asyncio
async def test_durable_guards_unjournaled_calls():
    """评审 #3/#4 + 评审16 🔴：durable 下未 journal 的有副作用/计费调用全硬拦（防重放重执行），
    含 kb.search / media.generate（评审16 指出此前漏拦——media 重放真重扣费）。"""
    t = FakeTransport(replies=["x"], call_agent_reply="sub")
    r = _run(t, durable=True, run_id="run-1")
    # coroutine 类：直接 await 触发守卫
    for coro in (
        r.call_agent("sub", input="q"),
        r.complete(user="q", schema=int),  # 结构化输出路径
        r.gather([("a", "q")]),
        r.route("q", [("a", "x"), ("b", "y")]),
        r.kb.search("q"),              # 评审16 🔴 此前漏拦
        r.media.generate(kind="image", prompt="cat"),  # 评审16 🔴 重放真重出图/重扣费
    ):
        with pytest.raises(RuntimeError, match="durable run 暂不支持"):
            await coro
    # async generator 类：守卫在生成器体首行，须迭代才触发
    for agen in (
        r.stream(user="q"),
        r.run_with_tools(user="q", tools=[]),
    ):
        with pytest.raises(RuntimeError, match="durable run 暂不支持"):
            async for _ in agen:
                pass


@pytest.mark.asyncio
async def test_durable_per_run_isolation():
    """不同 run_id 的 journal 互不串（ctx.memory 跨会话，run_id 隔离是正确性前提）。"""
    t = FakeTransport(replies=["run-A答案", "run-B答案"])
    a = await _run(t, durable=True, run_id="A").complete(user="x")
    b = await _run(t, durable=True, run_id="B").complete(user="x")
    assert a == "run-A答案" and b == "run-B答案"  # 各记各的，未因 idx 同为 0 串到一起
    assert len(t.invocations) == 2
