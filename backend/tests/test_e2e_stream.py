"""Phase 4 端到端流式冒烟

依赖 conftest 注入的 mock provider —— 它产 step + 2 个 delta + metadata + done
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from chameleon.app.main import create_app
from chameleon.providers.base import AGENTS, PROVIDERS
from chameleon.providers.base.protocol import Provider
from chameleon.providers.base.types import (
    AgentDef,
    InvokeContext,
    StreamEvent,
    StreamEventType,
)

# ── 客户端工厂 ─────────────────────────────────────────


@pytest_asyncio.fixture
async def stream_client() -> AsyncIterator[AsyncClient]:
    """专用 stream 客户端：raise_app_exceptions=False"""
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        yield c


# ── SSE 解析器 ─────────────────────────────────────────


def _parse_sse(body: str) -> list[dict[str, Any]]:
    """把整段 SSE 文本切成 [{"event": "...", "data": {...}}, ...]

    心跳行 `: ping` 跳过。
    """
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


# ── 基础流式 ────────────────────────────────────────────


async def test_stream_all_event_types(stream_client: AsyncClient, app_key: str) -> None:
    """mock provider 应 emit step + delta×2 + metadata + done"""
    async with stream_client.stream(
        "POST",
        "/v1/agents/mock-echo/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={"input": "hi", "stream": True},
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join([chunk async for chunk in r.aiter_text()])

    events = _parse_sse(body)
    types_seen = {e["event"] for e in events}
    assert "step" in types_seen
    assert "delta" in types_seen
    assert "done" in types_seen
    assert "error" not in types_seen

    # 拼出最终答案
    text = "".join(e["data"]["text"] for e in events if e["event"] == "delta")
    assert text == "echo: hi"


async def test_stream_multi_turn_history_replay(
    stream_client: AsyncClient, app_key: str
) -> None:
    """流式两轮 + 历史正确回放"""
    headers = {"Authorization": f"Bearer {app_key}"}

    async with stream_client.stream(
        "POST",
        "/v1/agents/mock-echo/invoke",
        headers=headers,
        json={"input": "round1", "stream": True},
    ) as r:
        body1 = "".join([c async for c in r.aiter_text()])
    events1 = _parse_sse(body1)
    done1 = next(e for e in events1 if e["event"] == "done")
    sid = done1["data"]["session_id"]

    async with stream_client.stream(
        "POST",
        "/v1/agents/mock-echo/invoke",
        headers=headers,
        json={"input": "round2", "session_id": sid, "stream": True},
    ) as r:
        body2 = "".join([c async for c in r.aiter_text()])
    events2 = _parse_sse(body2)
    assert next(e for e in events2 if e["event"] == "done")["data"]["session_id"] == sid

    # /messages 应该有 4 条（2 轮 user + assistant）
    msgs = await stream_client.get(
        f"/v1/conversations/{sid}/messages",
        headers=headers,
    )
    contents = [m["content"] for m in msgs.json()["data"]["items"]]
    assert contents == [
        "round1",
        "echo: round1",
        "round2",
        "echo: round2",
    ]


async def test_stream_list_messages_input_no_session_history(
    stream_client: AsyncClient, app_key: str
) -> None:
    """list[Message] 流式模式不消费 session 历史，但末条 user 仍落库"""
    headers = {"Authorization": f"Bearer {app_key}"}

    # 先建一轮制造历史
    async with stream_client.stream(
        "POST",
        "/v1/agents/mock-echo/invoke",
        headers=headers,
        json={"input": "前置", "stream": True},
    ) as r:
        body1 = "".join([c async for c in r.aiter_text()])
    sid = _parse_sse(body1)
    sid = next(e for e in sid if e["event"] == "done")["data"]["session_id"]

    async with stream_client.stream(
        "POST",
        "/v1/agents/mock-echo/invoke",
        headers=headers,
        json={
            "input": [
                {"role": "user", "content": "客户端历史 1"},
                {"role": "assistant", "content": "客户端历史 2"},
                {"role": "user", "content": "当前轮"},
            ],
            "session_id": sid,
            "stream": True,
        },
    ) as r:
        body2 = "".join([c async for c in r.aiter_text()])
    events2 = _parse_sse(body2)
    text = "".join(e["data"]["text"] for e in events2 if e["event"] == "delta")
    assert text == "echo: 当前轮"

    msgs = await stream_client.get(
        f"/v1/conversations/{sid}/messages",
        headers=headers,
    )
    contents = [m["content"] for m in msgs.json()["data"]["items"]]
    assert contents == ["前置", "echo: 前置", "当前轮", "echo: 当前轮"]


# ── 失败路径 ────────────────────────────────────────────


class _FailingProvider(Provider):
    """专测 provider 错误 → SSE error event + 不落 assistant msg"""

    name = "failing"

    async def stream(self, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        # 先 emit 一个 delta，再抛 ProviderError
        from chameleon.core.api.exceptions import ProviderUnreachableError

        yield StreamEvent(type=StreamEventType.delta, data={"text": "partial..."})
        raise ProviderUnreachableError(message="mock upstream down")


@pytest_asyncio.fixture
async def failing_agent() -> AsyncIterator[None]:
    PROVIDERS["failing"] = _FailingProvider()
    AGENTS["fail-agent"] = AgentDef(
        key="fail-agent",
        provider="failing",
        description="provider that always fails mid-stream",
    )
    yield
    PROVIDERS.pop("failing", None)
    AGENTS.pop("fail-agent", None)


async def test_stream_provider_failure_emits_error_no_assistant_msg(
    stream_client: AsyncClient,
    app_key: str,
    failing_agent: None,
) -> None:
    """provider 流中抛错 → error event；user msg 已落，assistant 不落"""
    headers = {"Authorization": f"Bearer {app_key}"}

    async with stream_client.stream(
        "POST",
        "/v1/agents/fail-agent/invoke",
        headers=headers,
        json={"input": "trigger fail", "stream": True},
    ) as r:
        body = "".join([c async for c in r.aiter_text()])
    events = _parse_sse(body)
    types_seen = {e["event"] for e in events}
    assert "error" in types_seen
    err = next(e for e in events if e["event"] == "error")
    assert err["data"]["code"] == 60020  # ProviderUnreachable

    # 找 session_id：error 事件没带，从 conversation 列表查最新的
    convs = await stream_client.get(
        "/v1/conversations?agent_key=fail-agent",
        headers=headers,
    )
    items = convs.json()["data"]["items"]
    assert items, "session 应已建立"
    sid = items[0]["session_id"]

    msgs = await stream_client.get(
        f"/v1/conversations/{sid}/messages",
        headers=headers,
    )
    contents = [m["content"] for m in msgs.json()["data"]["items"]]
    # 只有 user，没有 assistant（A3）
    assert contents == ["trigger fail"]


async def test_stream_failure_recorded_in_call_logs(
    stream_client: AsyncClient,
    admin_key: str,
    app_key: str,
    failing_agent: None,
) -> None:
    """流式失败也要进 call_log（success=False, code=60020）"""
    headers = {"Authorization": f"Bearer {app_key}"}

    async with stream_client.stream(
        "POST",
        "/v1/agents/fail-agent/invoke",
        headers=headers,
        json={"input": "x", "stream": True},
    ) as r:
        async for _ in r.aiter_text():
            pass

    logs = await stream_client.get(
        "/v1/admin/call-logs?success=false",
        headers={"Authorization": f"Bearer {admin_key}"},
    )
    items = logs.json()["data"]["items"]
    found = next(
        (log for log in items if log["agent_key"] == "fail-agent"),
        None,
    )
    assert found is not None
    assert found["stream"] is True
    assert found["success"] is False
    assert found["code"] == 60020


# ── 兼容性 ──────────────────────────────────────────────


async def test_done_event_data_is_complete_invoke_result(
    stream_client: AsyncClient, app_key: str
) -> None:
    """done event 的 data 字段应与非流模式响应同源（A 设计）"""
    async with stream_client.stream(
        "POST",
        "/v1/agents/mock-echo/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={"input": "compat-test", "stream": True},
    ) as r:
        body = "".join([c async for c in r.aiter_text()])
    events = _parse_sse(body)
    done = next(e for e in events if e["event"] == "done")
    # done.data 是 service 层增强后的完整 InvokeResult shape
    assert done["data"]["session_id"].startswith("sess_")
    assert done["data"]["answer"] == "echo: compat-test"
    # 同时整段 events 能拼出同样答案
    text = "".join(e["data"]["text"] for e in events if e["event"] == "delta")
    assert text == "echo: compat-test"


# 用 _ = pytest 保持 import
_ = pytest
