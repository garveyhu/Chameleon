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
async def test_call_agent_inprocess_key_unaffected(monkeypatch):
    """进程内 key（非 URL）仍走 a2a_bridge，不受 URL 路由影响。"""
    import chameleon.providers.base.a2a_bridge as bridge

    async def _caller(*, source, target, input, trace_id, budget_remaining, depth):
        return {"answer": f"inproc-{target}", "tokens": 5}

    monkeypatch.setattr(bridge, "get_a2a_caller", lambda: _caller)
    t = InProcessTransport(agent_key="x", bindings={}, slots={}, request_id="r1")
    out = await t.call_agent("some-key", input="q")
    assert out == "inproc-some-key"
