"""开放 A2A Slice A.2：InProcessTransport.call_agent 的 URL 路由——target 是 http(s) → 走
A2AClient 调远程（respx 拦）；未在 call_agents 白名单的远程 URL 拒绝（防任意 egress）。"""

from __future__ import annotations

import httpx
import pytest
import respx

from chameleon.providers.local.agentkit_runner import InProcessTransport

_URL = "https://remote.example/agent"


@pytest.mark.asyncio
async def test_call_agent_routes_url_to_remote_a2a():
    t = InProcessTransport(
        agent_key="x", bindings={}, slots={}, request_id="r1",
        budget=100_000, call_agents=[_URL],
    )
    with respx.mock:
        respx.post(_URL).mock(return_value=httpx.Response(200, json={
            "jsonrpc": "2.0", "id": "x",
            "result": {"kind": "message", "parts": [{"kind": "text", "text": "远程答案"}]},
        }))
        out = await t.call_agent(_URL, input="q")
    assert out == "远程答案"
    assert t._budget < 100_000  # 远程调用按本地估算扣了预算（成本闸对远程也生效）


@pytest.mark.asyncio
async def test_call_agent_remote_undeclared_denied():
    """未在 call_agents 声明的远程 URL → 拒（防任意网络出站 / SSRF）。"""
    t = InProcessTransport(
        agent_key="x", bindings={}, slots={}, request_id="r1", call_agents=[],
    )
    with pytest.raises(RuntimeError, match="未声明"):
        await t.call_agent("https://evil.example/agent", input="q")


@pytest.mark.asyncio
async def test_sandboxed_agent_remote_a2a_denied():
    """评审19 #1：沙箱(不可信)agent 禁出站远程 A2A（broker 在主进程有网会绕过 --network none）。"""
    t = InProcessTransport(
        agent_key="x", bindings={}, slots={}, request_id="r1",
        call_agents=[_URL], sandboxed=True,
    )
    with pytest.raises(RuntimeError, match="沙箱"):
        await t.call_agent(_URL, input="q")


@pytest.mark.asyncio
async def test_remote_a2a_depth_cap():
    """评审19 #3：A2A 深度超限拒，防跨系统环无限递归。"""
    t = InProcessTransport(
        agent_key="x", bindings={}, slots={}, request_id="r1",
        call_agents=[_URL], a2a_depth=5,  # +1 > _A2A_MAX_DEPTH(5)
    )
    with pytest.raises(RuntimeError, match="深度超限"):
        await t.call_agent(_URL, input="q")


@pytest.mark.asyncio
async def test_gather_routes_url_to_remote_a2a():
    """评审34 一致性 bug：gather 的 URL 分支也须走远程 A2A（与 call_agent 一致）——此前 gather 只用
    进程内 caller，把 URL 当 agent key 解析→失败。并发扇出远程 + 统一扣预算。"""
    t = InProcessTransport(
        agent_key="x", bindings={}, slots={}, request_id="r1",
        budget=100_000, call_agents=[_URL],
    )
    with respx.mock:
        respx.post(_URL).mock(return_value=httpx.Response(200, json={
            "jsonrpc": "2.0", "id": "x",
            "result": {"kind": "message", "parts": [{"kind": "text", "text": "远程并发答"}]},
        }))
        outs = await t.gather([(_URL, "q1"), (_URL, "q2")])
    assert outs == ["远程并发答", "远程并发答"]  # 保序 + 两支都真调远程
    assert t._budget < 100_000  # 远程分支也统一扣了预算（成本闸对 gather 远程分支生效）


@pytest.mark.asyncio
async def test_gather_url_respects_sandbox_deny():
    """gather 的 URL 分支同样受沙箱 egress 红线约束（复用 _remote_a2a_call 的全部红线）。"""
    t = InProcessTransport(agent_key="x", bindings={}, slots={}, request_id="r1",
                           call_agents=[_URL], sandboxed=True)
    with pytest.raises(RuntimeError, match="沙箱"):
        await t.gather([(_URL, "q")])


@pytest.mark.asyncio
async def test_call_agent_inprocess_key_unaffected(monkeypatch):
    """进程内 key（非 URL）仍走 a2a_bridge，不受 URL 路由影响。"""
    import chameleon.providers.base.a2a_bridge as bridge

    async def _caller(*, source, target, input, trace_id, budget_remaining, depth):
        return {"answer": f"inproc-{target}", "tokens": 5}

    monkeypatch.setattr(bridge, "get_a2a_caller", lambda: _caller)
    t = InProcessTransport(agent_key="x", bindings={}, slots={}, request_id="r1")
    out = await t.call_agent("some-key", input="q")
    assert out == "inproc-some-key"
