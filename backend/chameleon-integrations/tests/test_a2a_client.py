"""开放 A2A Slice A 客户端：AgentCard 发现 + message/send 往返（respx 拦远程 A2A 端点，零网络）。"""

from __future__ import annotations

import httpx
import pytest
import respx

from chameleon.integrations.a2a import A2AClient, A2AError

_BASE = "https://remote.example/agent"


def _rpc_ok(result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": "x", "result": result}


@pytest.mark.asyncio
async def test_agent_card_discovery():
    with respx.mock:
        respx.get(f"{_BASE}/.well-known/agent.json").mock(
            return_value=httpx.Response(200, json={"name": "远程助手", "url": _BASE,
                                                    "capabilities": {"streaming": True}})
        )
        card = await A2AClient(_BASE).agent_card()
    assert card["name"] == "远程助手" and card["capabilities"]["streaming"]


@pytest.mark.asyncio
async def test_call_parses_task_artifact():
    """message/send 返 Task（completed + artifacts）→ 抽 artifact 文本。"""
    with respx.mock:
        respx.post(_BASE).mock(return_value=httpx.Response(200, json=_rpc_ok({
            "kind": "task", "id": "t1", "status": {"state": "completed"},
            "artifacts": [{"parts": [{"kind": "text", "text": "远程答案"}]}],
        })))
        out = await A2AClient(_BASE).call("你好", trace_id="trace-1")
    assert out == "远程答案"


@pytest.mark.asyncio
async def test_call_parses_message_result():
    """result.kind=='message'（直接消息回复）→ 抽 parts 文本。"""
    with respx.mock:
        respx.post(_BASE).mock(return_value=httpx.Response(200, json=_rpc_ok({
            "kind": "message", "role": "agent",
            "parts": [{"kind": "text", "text": "直接回复"}],
        })))
        out = await A2AClient(_BASE).call("hi")
    assert out == "直接回复"


@pytest.mark.asyncio
async def test_call_raises_on_jsonrpc_error():
    with respx.mock:
        respx.post(_BASE).mock(return_value=httpx.Response(
            200, json={"jsonrpc": "2.0", "id": "x", "error": {"code": -32600, "message": "bad"}}))
        with pytest.raises(A2AError, match="JSON-RPC error"):
            await A2AClient(_BASE).call("hi")


@pytest.mark.asyncio
async def test_call_raises_on_task_failed_and_input_required():
    for state, match in (("failed", "task failed"), ("input-required", "input-required")):
        with respx.mock:
            respx.post(_BASE).mock(return_value=httpx.Response(200, json=_rpc_ok({
                "kind": "task", "id": "t", "status": {"state": state},
            })))
            with pytest.raises(A2AError, match=match):
                await A2AClient(_BASE).call("hi")
