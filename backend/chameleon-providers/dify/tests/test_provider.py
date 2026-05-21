"""DifyProvider 集成测试 —— respx mock SSE"""

import pytest
from httpx import Response

from chameleon.core.api.exceptions import ProviderConfigError
from chameleon.providers.base.types import AgentDef, InvokeContext, StreamEventType
from chameleon.providers.dify.provider import DifyProvider


def _agent_def(mode: str = "chat") -> AgentDef:
    return AgentDef(
        key="test-dify",
        provider="dify",
        config={
            "endpoint": "http://dify.test/v1",
            "app_id": "app-x",
            "api_key_env": "TEST_DIFY_KEY",
            "mode": mode,
        },
    )


def _ctx(
    agent_def: AgentDef,
    *,
    input_text: str = "hi",
    provider_conv_id: str | None = None,
) -> InvokeContext:
    return InvokeContext(
        agent_def=agent_def,
        input=input_text,
        history=[],
        session_id="sess_t",
        provider_conv_id=provider_conv_id,
        app_id="app1",
        stream=True,
    )


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch):
    monkeypatch.setenv("TEST_DIFY_KEY", "app-test-key")


async def test_dify_chat_stream_delta_and_done(respx_mock) -> None:
    sse_body = (
        'data: {"event":"message","conversation_id":"dify-conv-1","answer":"hello"}\n\n'
        'data: {"event":"message","conversation_id":"dify-conv-1","answer":" world"}\n\n'
        'data: {"event":"message_end","conversation_id":"dify-conv-1","metadata":{"usage":{"prompt_tokens":10,"completion_tokens":2,"total_tokens":12}}}\n\n'
    )
    respx_mock.post("http://dify.test/v1/chat-messages").mock(
        return_value=Response(200, text=sse_body)
    )

    provider = DifyProvider()
    events = [ev async for ev in provider.stream(_ctx(_agent_def()))]
    types_seen = {e.type for e in events}

    assert StreamEventType.delta in types_seen
    assert StreamEventType.done in types_seen
    assert StreamEventType.error not in types_seen

    # 拼接 delta
    text = "".join(e.data["text"] for e in events if e.type == StreamEventType.delta)
    assert text == "hello world"

    # done 携带 provider_conv_id
    done = next(e for e in events if e.type == StreamEventType.done)
    assert done.data["provider_conv_id"] == "dify-conv-1"


async def test_dify_chat_invoke_aggregates(respx_mock) -> None:
    """非流式 invoke 默认聚合 stream"""
    sse_body = (
        'data: {"event":"message","conversation_id":"c1","answer":"今天"}\n\n'
        'data: {"event":"message","conversation_id":"c1","answer":"销售额"}\n\n'
        'data: {"event":"message_end","conversation_id":"c1","metadata":{"usage":{"total_tokens":42}}}\n\n'
    )
    respx_mock.post("http://dify.test/v1/chat-messages").mock(
        return_value=Response(200, text=sse_body)
    )

    provider = DifyProvider()
    result = await provider.invoke(_ctx(_agent_def()))
    assert result.answer == "今天销售额"
    assert result.provider_conv_id == "c1"
    assert result.usage and result.usage.total_tokens == 42


async def test_dify_chat_transmits_conv_id_when_present(respx_mock) -> None:
    """带 provider_conv_id 调用时，HTTP 请求 body 必须含 conversation_id"""
    route = respx_mock.post("http://dify.test/v1/chat-messages").mock(
        return_value=Response(
            200,
            text='data: {"event":"message_end","conversation_id":"existing","metadata":{}}\n\n',
        )
    )

    provider = DifyProvider()
    [_ async for _ in provider.stream(_ctx(_agent_def(), provider_conv_id="existing"))]

    sent = route.calls[0].request.read().decode()
    assert '"conversation_id":"existing"' in sent


async def test_dify_http_401_raises_auth_error(respx_mock) -> None:
    from chameleon.core.api.exceptions import ProviderAuthError

    respx_mock.post("http://dify.test/v1/chat-messages").mock(
        return_value=Response(401, text='{"code":"invalid_api_key"}')
    )

    provider = DifyProvider()
    with pytest.raises(ProviderAuthError):
        async for _ in provider.stream(_ctx(_agent_def())):
            pass


async def test_dify_missing_env_key_fail_fast(monkeypatch) -> None:
    monkeypatch.delenv("TEST_DIFY_KEY")
    provider = DifyProvider()
    with pytest.raises(ProviderConfigError):
        async for _ in provider.stream(_ctx(_agent_def())):
            pass
