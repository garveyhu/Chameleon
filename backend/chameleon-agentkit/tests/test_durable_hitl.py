"""durable Slice2 —— HITL 暂停/恢复（ctx.ask_human + AgentPaused）。

核心 e2e（无需 provider，FakeTransport 即可验机制）：handle 跑到 ask_human 无答案 → 抛
AgentPaused + 落 pending → 回填答案 → 重新 invoke，complete 重放（不重调模型）+ ask 返答案续跑。
"""

from __future__ import annotations

import pytest

from chameleon.agentkit import AgentPaused, AgentRun
from chameleon.agentkit.testing import FakeTransport


def _run(t: FakeTransport, *, durable: bool = False, run_id: str | None = None) -> AgentRun:
    return AgentRun(
        transport=t, agent_key="a", query="q", messages=[], history=[],
        session_id=None, config={}, durable=durable, run_id=run_id,
    )


async def _drive(ctx: AgentRun, handle) -> list[str]:  # noqa: ANN001
    out: list[str] = []
    async for d in handle(ctx):
        out.append(d)
    return out


async def _approval_handle(ctx: AgentRun):
    greeting = await ctx.complete(user="打个招呼")        # call_index 0
    decision = await ctx.ask_human("批准这步操作吗？")     # call_index 1（暂停点）
    yield f"{greeting}/{decision}"


@pytest.mark.asyncio
async def test_ask_human_pauses_and_persists_pending():
    t = FakeTransport(replies=["你好"])
    with pytest.raises(AgentPaused) as ei:
        await _drive(_run(t, durable=True, run_id="r1"), _approval_handle)
    paused = ei.value
    assert paused.call_index == 1 and paused.prompt == "批准这步操作吗？"
    pending = await t.memory_get("__chm_pending__")
    # pending 含 call_index/prompt/run_id + 原始 query（resume 用它重放，见 Slice C）
    assert pending["call_index"] == 1 and pending["prompt"] == "批准这步操作吗？"
    assert pending["run_id"] == "r1" and pending["query"] == "q"


@pytest.mark.asyncio
async def test_full_pause_resolve_resume_cycle():
    t = FakeTransport(replies=["你好"])  # 仅 1 个 reply：证重放不再调模型

    # 首跑：complete 记录 + 调模型 1 次；ask_human 暂停
    with pytest.raises(AgentPaused):
        await _drive(_run(t, durable=True, run_id="r1"), _approval_handle)
    assert len(t.invocations) == 1

    # 人答复经框架 resume API 回填 journal（resume 端点/run_agentkit 干的事）@ask 的 call_index=1
    resume_ctx = _run(t, durable=True, run_id="r1")
    await resume_ctx._seed_resume(1, "同意")

    # 重放：complete@0 取记录值不重调模型 + ask@1 返答案 → handle 续跑完成
    out = await _drive(resume_ctx, _approval_handle)
    assert out == ["你好/同意"]
    assert len(t.invocations) == 1  # +0：重放零模型调用（省钱/不重复副作用）


@pytest.mark.asyncio
async def test_ask_human_requires_durable():
    t = FakeTransport(replies=["x"])
    with pytest.raises(RuntimeError, match="需 durable"):
        await _drive(_run(t), _approval_handle)  # durable 默认关


@pytest.mark.asyncio
async def test_resume_one_time_no_decision_flip():
    """评审20 🔴：ask 点一旦恢复，不可用不同答案再恢复（防翻转已审批决策 + 重放审批后副作用）；
    同答案重复恢复幂等放行（允许重试）。"""
    t = FakeTransport(replies=["你好"])
    # 先跑到暂停（落 pending @call_index 1）
    with pytest.raises(AgentPaused):
        await _drive(_run(t, durable=True, run_id="r1"), _approval_handle)
    ctx = _run(t, durable=True, run_id="r1")
    await ctx._seed_resume(1, "同意")              # 首次恢复
    await ctx._seed_resume(1, "同意")              # 同答案幂等：不报错
    with pytest.raises(RuntimeError, match="不可翻转"):
        await ctx._seed_resume(1, "拒绝")          # 不同答案：拒（防决策翻转）
