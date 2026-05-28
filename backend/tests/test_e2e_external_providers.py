"""Phase 6 端到端：DIFY / FastGPT 外部 provider 通过统一 invoke 调通

策略：运行时挂临时 AgentDef 到 AGENTS，用 respx 拦截 HTTP 调用，
     验证 Chameleon 统一 invoke API 路径打通到外部 provider。
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from chameleon.app.main import create_app
from chameleon.providers.base import AGENTS
from chameleon.providers.base.types import AgentDef


def _parse_sse(body: str) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for block in re.split(r"\n\n+", body):
        block = block.strip("\n")
        if not block or block.startswith(":"):
            continue
        event_name = None
        data_str = None
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_str = line[len("data:") :].strip()
        if event_name is None or data_str is None:
            continue
        parsed.append({"event": event_name, "data": json.loads(data_str)})
    return parsed


@pytest_asyncio.fixture
async def stream_client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        yield c


# ── DIFY ────────────────────────────────────────────────


@pytest_asyncio.fixture
async def dify_agent_setup(monkeypatch) -> AsyncIterator[str]:
    """注入 dify-faq agent + 设 env var"""
    monkeypatch.setenv("TEST_DIFY_FAQ_KEY", "dify-app-fake-key")
    AGENTS["dify-faq"] = AgentDef(
        key="dify-faq",
        provider="dify",
        description="mock DIFY FAQ agent",
        config={
            "endpoint": "http://dify.test/v1",
            "app_id": "fake-app",
            "api_key_env": "TEST_DIFY_FAQ_KEY",
            "mode": "chat",
        },
    )
    yield "dify-faq"
    AGENTS.pop("dify-faq", None)


async def test_dify_invoke_non_stream(
    client: AsyncClient,
    app_key: str,
    dify_agent_setup: str,
    respx_mock,
) -> None:
    """非流式调 DIFY agent → 验证 answer + provider_conv_id 双写"""
    sse_body = (
        'data: {"event":"message","conversation_id":"dify-conv-abc","answer":"hi"}\n\n'
        'data: {"event":"message","conversation_id":"dify-conv-abc","answer":" there"}\n\n'
        'data: {"event":"message_end","conversation_id":"dify-conv-abc",'
        '"metadata":{"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}}}\n\n'
    )
    respx_mock.post("http://dify.test/v1/chat-messages").mock(
        return_value=__import__("httpx").Response(200, text=sse_body)
    )

    r = await client.post(
        "/v1/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={"input": "你好", "stream": False, "agent_key": dify_agent_setup},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"]
    data = body["data"]
    assert data["answer"] == "hi there"
    assert data["usage"]["total_tokens"] == 5

    sid = data["session_id"]
    # 第二轮验证 provider_conv_id 透传（agent 应能收到 conversation_id 参数）
    route = respx_mock.post("http://dify.test/v1/chat-messages").mock(
        return_value=__import__("httpx").Response(
            200,
            text='data: {"event":"message","conversation_id":"dify-conv-abc","answer":"再见"}\n\n'
            'data: {"event":"message_end","conversation_id":"dify-conv-abc","metadata":{}}\n\n',
        )
    )
    r2 = await client.post(
        "/v1/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={
            "input": "再说一遍",
            "session_id": sid,
            "stream": False,
            "agent_key": dify_agent_setup,
        },
    )
    assert r2.status_code == 200
    sent = route.calls[-1].request.read().decode()
    assert '"conversation_id":"dify-conv-abc"' in sent


async def test_dify_invoke_stream(
    stream_client: AsyncClient,
    app_key: str,
    dify_agent_setup: str,
    respx_mock,
) -> None:
    """流式调 DIFY agent → 验证 delta + done 事件"""
    sse_body = (
        'data: {"event":"message","conversation_id":"c1","answer":"流式"}\n\n'
        'data: {"event":"message","conversation_id":"c1","answer":"回复"}\n\n'
        'data: {"event":"message_end","conversation_id":"c1","metadata":{}}\n\n'
    )
    respx_mock.post("http://dify.test/v1/chat-messages").mock(
        return_value=__import__("httpx").Response(200, text=sse_body)
    )

    async with stream_client.stream(
        "POST",
        "/v1/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={"input": "test", "stream": True, "agent_key": dify_agent_setup},
    ) as r:
        body = "".join([c async for c in r.aiter_text()])
    events = _parse_sse(body)
    types_seen = {e["event"] for e in events}
    assert "delta" in types_seen
    assert "done" in types_seen
    delta_text = "".join(e["data"]["text"] for e in events if e["event"] == "delta")
    assert delta_text == "流式回复"


# ── FastGPT ─────────────────────────────────────────────


@pytest_asyncio.fixture
async def fastgpt_agent_setup(monkeypatch) -> AsyncIterator[str]:
    monkeypatch.setenv("TEST_FASTGPT_ORDER_KEY", "fastgpt-fake-key")
    AGENTS["fastgpt-order"] = AgentDef(
        key="fastgpt-order",
        provider="fastgpt",
        description="mock FastGPT order agent",
        config={
            "endpoint": "http://fastgpt.test/api",
            "app_id": "fastgpt-app",
            "api_key_env": "TEST_FASTGPT_ORDER_KEY",
        },
    )
    yield "fastgpt-order"
    AGENTS.pop("fastgpt-order", None)


async def test_fastgpt_invoke_non_stream(
    client: AsyncClient,
    app_key: str,
    fastgpt_agent_setup: str,
    respx_mock,
) -> None:
    sse_body = (
        "event: answer\n"
        'data: {"choices":[{"delta":{"content":"foo"},"index":0}]}\n\n'
        "event: answer\n"
        'data: {"choices":[{"delta":{"content":"bar"},"index":0}]}\n\n'
        "event: answer\n"
        'data: {"choices":[{"delta":{"content":""},"finish_reason":"stop","index":0}],'
        '"usage":{"prompt_tokens":2,"completion_tokens":2,"total_tokens":4}}\n\n'
        "data: [DONE]\n\n"
    )
    respx_mock.post("http://fastgpt.test/api/v1/chat/completions").mock(
        return_value=__import__("httpx").Response(200, text=sse_body)
    )

    r = await client.post(
        "/v1/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={"input": "query", "stream": False, "agent_key": fastgpt_agent_setup},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    data = body["data"]
    assert data["answer"] == "foobar"
    assert data["usage"]["total_tokens"] == 4


async def test_fastgpt_invoke_stream(
    stream_client: AsyncClient,
    app_key: str,
    fastgpt_agent_setup: str,
    respx_mock,
) -> None:
    sse_body = (
        "event: flowNodeStatus\n"
        'data: {"status":"completed","name":"order_lookup"}\n\n'
        "event: answer\n"
        'data: {"choices":[{"delta":{"content":"订单"},"index":0}]}\n\n'
        "event: answer\n"
        'data: {"choices":[{"delta":{"content":"已发货"},"index":0}]}\n\n'
        "event: answer\n"
        'data: {"choices":[{"delta":{"content":""},"finish_reason":"stop","index":0}]}\n\n'
        "data: [DONE]\n\n"
    )
    respx_mock.post("http://fastgpt.test/api/v1/chat/completions").mock(
        return_value=__import__("httpx").Response(200, text=sse_body)
    )

    async with stream_client.stream(
        "POST",
        "/v1/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={"input": "我的订单", "stream": True, "agent_key": fastgpt_agent_setup},
    ) as r:
        body = "".join([c async for c in r.aiter_text()])
    events = _parse_sse(body)
    types_seen = {e["event"] for e in events}
    assert "delta" in types_seen
    assert "step" in types_seen  # flowNodeStatus → step
    assert "done" in types_seen

    delta_text = "".join(e["data"]["text"] for e in events if e["event"] == "delta")
    assert delta_text == "订单已发货"

    step_names = {e["data"].get("name") for e in events if e["event"] == "step"}
    assert "order_lookup" in step_names


# ── 配置错误路径 ────────────────────────────────────────


async def test_dify_missing_env_returns_provider_error(
    client: AsyncClient,
    app_key: str,
    monkeypatch,
) -> None:
    """agent 配置 api_key_env 指向未设的 env → ProviderConfigError"""
    AGENTS["dify-noenv"] = AgentDef(
        key="dify-noenv",
        provider="dify",
        config={
            "endpoint": "http://dify.test/v1",
            "api_key_env": "MISSING_ENV_VAR_XYZ",
            "mode": "chat",
        },
    )
    try:
        monkeypatch.delenv("MISSING_ENV_VAR_XYZ", raising=False)
        r = await client.post(
            "/v1/invoke",
            headers={"Authorization": f"Bearer {app_key}"},
            json={"input": "x", "stream": False, "agent_key": "dify-noenv"},
        )
        body = r.json()
        assert body["success"] is False
        # ProviderConfigError 是 BusinessError 子类 → handler 接管
        assert body["code"] == 60010
    finally:
        AGENTS.pop("dify-noenv", None)


_ = asyncio  # 保留 import
