"""A2A 原语一致性保护（评审34 续）：route / handoff 必须经 self.call_agent 委托——这样 transport
的 URL 路由（http(s) target → 远程 A2A）对它们同样生效，与 ctx.call_agent / ctx.gather 一致。
gather 曾因直连 in-process caller 绕过路由（已修，commit 25b3f07）；本测防 route/handoff 将来被
重构成绕过 call_agent 而悄悄丢掉远程 A2A 能力。
"""

from __future__ import annotations

import pytest

from chameleon.agentkit import AgentRun
from chameleon.agentkit.testing import FakeTransport


class _SpyTransport(FakeTransport):
    """记录 call_agent 收到的 target——验证 route/handoff 确实委托到 call_agent。"""

    def __init__(self) -> None:
        super().__init__(replies=[])
        self.routed: list[str] = []

    async def call_agent(self, target: str, *, input: str) -> str:
        self.routed.append(target)
        return f"ans-from-{target}"


def _run(t: FakeTransport) -> AgentRun:
    return AgentRun(transport=t, agent_key="a", query="q", messages=[], history=[],
                    session_id=None, config={})


@pytest.mark.asyncio
async def test_handoff_delegates_to_call_agent():
    """handoff → self.call_agent，故 URL 目标（远程 A2A）经 transport 路由同样生效。"""
    t = _SpyTransport()
    out = await _run(t).handoff("https://remote.example/a2a/x", instruction="接手")
    assert t.routed == ["https://remote.example/a2a/x"]
    assert "ans-from-https://remote.example/a2a/x" in out


@pytest.mark.asyncio
async def test_route_single_candidate_delegates_to_call_agent():
    """route 单候选直接 call_agent（不调模型）——候选是 URL 时也走远程 A2A 路由。"""
    t = _SpyTransport()
    out = await _run(t).route("q", [("https://remote.example/a2a/y", "远程专家")])
    assert t.routed == ["https://remote.example/a2a/y"]
    assert out == "ans-from-https://remote.example/a2a/y"
