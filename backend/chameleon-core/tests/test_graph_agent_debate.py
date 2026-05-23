"""P20.4 PR #56 单元测试：AgentDebateNode 状态机 + 红线"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import pytest

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.nodes.agent_debate import (
    MAX_ROUNDS_HARD_CAP,
    AgentDebateNode,
)
from chameleon.core.graph.types import NodeSpec
from chameleon.providers.base import (
    AGENTS,
    PROVIDERS,
    AgentDef,
    InvokeContext,
    InvokeResult,
    Provider,
    StreamEvent,
    StreamEventType,
    Usage,
)


class _RecordedProvider(Provider):
    """根据 agent.key 返回 scripted 回答，记录调用次数"""

    name = "debate-stub"

    def __init__(self) -> None:
        self.calls: list[str] = []
        # key → list of answers（按顺序消费）
        self.scripts: dict[str, list[str]] = {}
        # key → 每次回答的 total_tokens
        self.token_per_call: dict[str, int] = {}
        # 模拟单次调用耗时（秒）—— 用于超时测试
        self.delay_sec: float = 0.0

    def script(self, agent_key: str, answers: list[str], tokens: int = 100):
        self.scripts[agent_key] = list(answers)
        self.token_per_call[agent_key] = tokens

    async def stream(self, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        if False:
            yield StreamEvent(type=StreamEventType.delta)

    async def invoke(self, ctx: InvokeContext) -> InvokeResult:
        key = ctx.agent_def.key
        self.calls.append(key)
        if self.delay_sec:
            await asyncio.sleep(self.delay_sec)
        answers = self.scripts.get(key) or ["..."]
        ans = answers.pop(0) if answers else "..."
        tokens = self.token_per_call.get(key, 100)
        return InvokeResult(
            answer=ans,
            session_id=ctx.session_id,
            request_id=ctx.request_id,
            usage=Usage(
                prompt_tokens=tokens // 2,
                completion_tokens=tokens - tokens // 2,
                total_tokens=tokens,
            ),
        )


@pytest.fixture
def debate_setup():
    p = _RecordedProvider()
    PROVIDERS["debate-stub"] = p
    for key in ("proposer", "critic", "judge", "critic2"):
        AGENTS[key] = AgentDef(key=key, provider="debate-stub", description="")
    try:
        yield p
    finally:
        PROVIDERS.pop("debate-stub", None)
        for key in ("proposer", "critic", "judge", "critic2"):
            AGENTS.pop(key, None)


def _make_ctx(request_id: str = "test-trace-001") -> NodeContext:
    return NodeContext(
        request_id=request_id,
        graph_id=1,
        graph_run_id=1,
        depth=0,
        started_at=datetime.now(timezone.utc),
    )


def _make_node(data: dict[str, Any]) -> AgentDebateNode:
    spec = NodeSpec(id="debate-1", type="agent_debate", data=data)
    return AgentDebateNode(spec)


# ── validate_data 红线 ──────────────────────────────────


def test_validate_requires_at_least_2_agents():
    with pytest.raises(ValueError, match="至少 2 个"):
        _make_node({"agents": ["only-one"]})


def test_validate_rejects_non_string_agent():
    with pytest.raises(ValueError, match="非空 str"):
        _make_node({"agents": ["a", 42]})  # type: ignore[list-item]


def test_validate_rejects_max_rounds_over_cap():
    with pytest.raises(ValueError, match=str(MAX_ROUNDS_HARD_CAP)):
        _make_node(
            {"agents": ["a", "b"], "max_rounds": MAX_ROUNDS_HARD_CAP + 1}
        )


def test_validate_rejects_bad_early_stop():
    with pytest.raises(ValueError, match="early_stop_on"):
        _make_node({"agents": ["a", "b"], "early_stop_on": "never"})


def test_validate_rejects_zero_timeout():
    with pytest.raises(ValueError, match="timeout_total_sec"):
        _make_node({"agents": ["a", "b"], "timeout_total_sec": 0})


# ── happy path ────────────────────────────────────────


async def test_max_rounds_reached_with_judge(debate_setup: _RecordedProvider):
    debate_setup.script("proposer", ["P1", "P2", "P3"], tokens=50)
    debate_setup.script(
        "critic", ["反对 P1", "依然反对", "还是不行"], tokens=50
    )
    debate_setup.script("judge", ["最终裁决"], tokens=80)

    node = _make_node(
        {
            "agents": ["proposer", "critic", "judge"],
            "max_rounds": 3,
            "early_stop_on": "max_rounds",
        }
    )
    out = await node.execute(_make_ctx(), {"topic": "测试议题"})
    assert out["stopped_reason"] == "max_rounds"
    assert len(out["rounds"]) == 3
    assert out["judge"]["agent"] == "judge"
    assert out["final_answer"] == "最终裁决"
    assert out["total_consumed_tokens"] >= 3 * (50 + 50) + 80


async def test_no_judge_uses_last_proposer_answer(
    debate_setup: _RecordedProvider,
):
    debate_setup.script("proposer", ["X1", "X2"], tokens=50)
    debate_setup.script("critic", ["反对", "依然反对"], tokens=50)

    node = _make_node(
        {
            "agents": ["proposer", "critic"],
            "max_rounds": 2,
            "early_stop_on": "max_rounds",
        }
    )
    out = await node.execute(_make_ctx(), "议题 X")
    assert out["judge"] is None
    assert out["final_answer"] == "X2"
    assert out["stopped_reason"] == "max_rounds"


async def test_consensus_short_circuit(debate_setup: _RecordedProvider):
    """critic 第二轮表态 agree → 应在第二轮后中断（含 judge 终局）"""
    debate_setup.script("proposer", ["P1", "P2", "P3"], tokens=50)
    debate_setup.script("critic", ["不行", "agree 没问题"], tokens=50)
    debate_setup.script("judge", ["接受"], tokens=50)

    node = _make_node(
        {
            "agents": ["proposer", "critic", "judge"],
            "max_rounds": 5,
            "early_stop_on": "consensus",
        }
    )
    out = await node.execute(_make_ctx(), "topic")
    assert out["stopped_reason"] == "consensus"
    assert len(out["rounds"]) == 2
    assert out["rounds"][-1]["agreed"] is True
    assert out["judge"]["answer"] == "接受"


async def test_consensus_disabled_when_early_stop_max_rounds(
    debate_setup: _RecordedProvider,
):
    """early_stop='max_rounds' 时即使 critic agree 也不提前停"""
    debate_setup.script("proposer", ["P1", "P2"], tokens=20)
    debate_setup.script("critic", ["agree first!", "still agree"], tokens=20)
    node = _make_node(
        {
            "agents": ["proposer", "critic"],
            "max_rounds": 2,
            "early_stop_on": "max_rounds",
        }
    )
    out = await node.execute(_make_ctx(), "t")
    assert out["stopped_reason"] == "max_rounds"
    assert len(out["rounds"]) == 2


async def test_multi_critic_all_must_agree(debate_setup: _RecordedProvider):
    """4 个 agent：proposer + 2 critics + judge；2 critic 都 agree 才算 consensus"""
    debate_setup.script("proposer", ["P1", "P2"], tokens=20)
    debate_setup.script("critic", ["agree", "agree"], tokens=20)
    debate_setup.script("critic2", ["nope", "agree"], tokens=20)
    debate_setup.script("judge", ["done"], tokens=20)
    node = _make_node(
        {
            "agents": ["proposer", "critic", "judge", "critic2"],
            "max_rounds": 5,
            "early_stop_on": "consensus",
        }
    )
    out = await node.execute(_make_ctx(), "t")
    assert out["stopped_reason"] == "consensus"
    # 第 1 轮 critic2 不同意 → 进第 2 轮；第 2 轮全 agree → 停
    assert len(out["rounds"]) == 2
    assert out["rounds"][0]["agreed"] is False
    assert out["rounds"][1]["agreed"] is True


async def test_timeout_stops_gracefully(debate_setup: _RecordedProvider):
    """timeout_total_sec=1 + provider 每次 sleep 0.6s → 1-2 轮后超时"""
    debate_setup.script(
        "proposer", ["P1", "P2", "P3", "P4", "P5"], tokens=10
    )
    debate_setup.script("critic", ["反对"] * 5, tokens=10)
    debate_setup.delay_sec = 0.6
    node = _make_node(
        {
            "agents": ["proposer", "critic"],
            "max_rounds": 5,
            "early_stop_on": "max_rounds",
            "timeout_total_sec": 1,
        }
    )
    out = await node.execute(_make_ctx(), "t")
    assert out["stopped_reason"] in ("timeout", "max_rounds")
    # 至少跑了 1 轮（已有 final_answer）
    assert out["final_answer"] != ""


async def test_budget_exhaustion_stops(debate_setup: _RecordedProvider):
    """total_budget 200 token，每次 100 → 跑不完 max_rounds=5"""
    debate_setup.script("proposer", ["P"] * 5, tokens=100)
    debate_setup.script("critic", ["反对"] * 5, tokens=100)
    node = _make_node(
        {
            "agents": ["proposer", "critic"],
            "max_rounds": 5,
            "early_stop_on": "max_rounds",
            "total_budget_tokens": 200,
        }
    )
    out = await node.execute(_make_ctx(), "t")
    assert out["stopped_reason"] in ("budget_exhausted", "max_rounds")
    assert out["total_consumed_tokens"] >= 200
