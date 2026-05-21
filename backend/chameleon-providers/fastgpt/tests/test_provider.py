"""FastGPTProvider 集成测试 —— respx mock OpenAI 兼容 SSE"""

import pytest
from httpx import Response

from chameleon.providers.base.types import AgentDef, InvokeContext, StreamEventType
from chameleon.providers.fastgpt.provider import FastGPTProvider


def _agent_def() -> AgentDef:
    return AgentDef(
        key="test-fastgpt",
        provider="fastgpt",
        config={
            "endpoint": "http://fastgpt.test/api",
            "app_id": "app-x",
            "api_key_env": "TEST_FASTGPT_KEY",
        },
    )


def _ctx(*, chat_id: str | None = None) -> InvokeContext:
    return InvokeContext(
        agent_def=_agent_def(),
        input="hi",
        history=[],
        session_id="sess_t",
        provider_conv_id=chat_id,
        app_id="app1",
        stream=True,
    )


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch):
    monkeypatch.setenv("TEST_FASTGPT_KEY", "fastgpt-test-key")


async def test_fastgpt_chat_stream(respx_mock) -> None:
    sse_body = (
        "event: answer\n"
        'data: {"choices":[{"delta":{"content":"hello"},"finish_reason":null,"index":0}]}\n\n'
        "event: answer\n"
        'data: {"choices":[{"delta":{"content":" world"},"finish_reason":null,"index":0}]}\n\n'
        "event: answer\n"
        'data: {"choices":[{"delta":{"content":""},"finish_reason":"stop","index":0}],"usage":{"prompt_tokens":5,"completion_tokens":2,"total_tokens":7}}\n\n'
        "data: [DONE]\n\n"
    )
    respx_mock.post("http://fastgpt.test/api/v1/chat/completions").mock(
        return_value=Response(200, text=sse_body)
    )

    provider = FastGPTProvider()
    events = [ev async for ev in provider.stream(_ctx())]
    types_seen = {e.type for e in events}

    assert StreamEventType.delta in types_seen
    assert StreamEventType.done in types_seen
    assert StreamEventType.error not in types_seen


async def test_fastgpt_invoke_aggregates(respx_mock) -> None:
    sse_body = (
        "event: answer\n"
        'data: {"choices":[{"delta":{"content":"a"},"index":0}]}\n\n'
        "event: answer\n"
        'data: {"choices":[{"delta":{"content":"b"},"index":0}]}\n\n'
        "event: answer\n"
        'data: {"choices":[{"delta":{"content":""},"finish_reason":"stop","index":0}],"usage":{"total_tokens":10}}\n\n'
        "data: [DONE]\n\n"
    )
    respx_mock.post("http://fastgpt.test/api/v1/chat/completions").mock(
        return_value=Response(200, text=sse_body)
    )

    provider = FastGPTProvider()
    result = await provider.invoke(_ctx())
    assert result.answer == "ab"
    assert result.usage and result.usage.total_tokens == 10


async def test_fastgpt_chat_id_transmitted(respx_mock) -> None:
    route = respx_mock.post("http://fastgpt.test/api/v1/chat/completions").mock(
        return_value=Response(
            200,
            text='event: answer\ndata: {"choices":[{"delta":{"content":""},"finish_reason":"stop","index":0}]}\n\ndata: [DONE]\n\n',
        )
    )
    provider = FastGPTProvider()
    [_ async for _ in provider.stream(_ctx(chat_id="chat-xyz"))]
    sent = route.calls[0].request.read().decode()
    assert '"chatId":"chat-xyz"' in sent


async def test_fastgpt_429_raises(respx_mock) -> None:
    from chameleon.core.api.exceptions import ProviderRateLimitError

    respx_mock.post("http://fastgpt.test/api/v1/chat/completions").mock(
        return_value=Response(429, text='{"err":"rate limit"}')
    )
    provider = FastGPTProvider()
    with pytest.raises(ProviderRateLimitError):
        async for _ in provider.stream(_ctx()):
            pass


async def test_fastgpt_flow_node_events(respx_mock) -> None:
    """detail=true 时 FastGPT 会 emit flowNodeStatus，应翻成 step"""
    sse_body = (
        "event: flowNodeStatus\n"
        'data: {"status":"completed","name":"intent_route"}\n\n'
        "event: answer\n"
        'data: {"choices":[{"delta":{"content":"ok"},"index":0}]}\n\n'
        "event: answer\n"
        'data: {"choices":[{"delta":{"content":""},"finish_reason":"stop","index":0}]}\n\n'
        "data: [DONE]\n\n"
    )
    respx_mock.post("http://fastgpt.test/api/v1/chat/completions").mock(
        return_value=Response(200, text=sse_body)
    )
    provider = FastGPTProvider()
    events = [ev async for ev in provider.stream(_ctx())]
    steps = [e for e in events if e.type == StreamEventType.step]
    assert any(s.data.get("name") == "intent_route" for s in steps)
