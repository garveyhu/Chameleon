"""三种本地 agent 范式端到端验证

本测试证明：
- echo（字典模式 + build_graph） —— v0.1 兼容
- echo-runnable（BaseAgent + LangChain Runnable） —— 范式 C
- echo-native（BaseAgent + 纯 Python） —— 范式 B
三种范式通过同一统一接口 POST /v1/agents/{key}/invoke 调用，对客户端完全透明。
"""

import json
import re
from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from chameleon.app.main import create_app


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


# ── 范式 A：echo（字典模式 + build_graph）已在其它测试覆盖 ────


# ── 范式 B：echo-native（纯 Python）─────────────────────


async def test_echo_native_non_stream(client: AsyncClient, app_key: str) -> None:
    r = await client.post(
        "/v1/agents/example-echo-native/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={"input": "hi", "stream": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"]
    data = body["data"]
    assert data["answer"] == "echo(native): hi"
    # 至少有 prepare step
    assert any(s["name"] == "prepare" for s in data["steps"])
    # native agent 自己 emit 了 usage
    assert data["usage"]["total_tokens"] > 0


async def test_echo_native_stream(stream_client: AsyncClient, app_key: str) -> None:
    async with stream_client.stream(
        "POST",
        "/v1/agents/example-echo-native/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={"input": "world", "stream": True},
    ) as r:
        assert r.status_code == 200
        body = "".join([c async for c in r.aiter_text()])

    events = _parse_sse(body)
    types_seen = {e["event"] for e in events}
    assert "step" in types_seen
    assert "delta" in types_seen
    assert "done" in types_seen
    delta_text = "".join(e["data"]["text"] for e in events if e["event"] == "delta")
    assert delta_text == "echo(native): world"


# ── 范式 C：echo-runnable（LangChain Runnable）─────────


async def test_echo_runnable_non_stream(client: AsyncClient, app_key: str) -> None:
    r = await client.post(
        "/v1/agents/example-echo-runnable/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={"input": "abc", "stream": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"]
    data = body["data"]
    assert data["answer"] == "echo(runnable): abc"


async def test_echo_runnable_stream(stream_client: AsyncClient, app_key: str) -> None:
    async with stream_client.stream(
        "POST",
        "/v1/agents/example-echo-runnable/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={"input": "lcel", "stream": True},
    ) as r:
        assert r.status_code == 200
        body = "".join([c async for c in r.aiter_text()])
    events = _parse_sse(body)
    types_seen = {e["event"] for e in events}
    assert "delta" in types_seen
    assert "done" in types_seen
    delta_text = "".join(e["data"]["text"] for e in events if e["event"] == "delta")
    assert delta_text == "echo(runnable): lcel"


# ── 客户端视角：三种范式调用方式完全一样 ──────────────


async def test_three_paradigms_uniform_interface(
    client: AsyncClient, app_key: str
) -> None:
    """三种范式的 invoke 响应结构完全一致，客户端代码可以共用"""
    headers = {"Authorization": f"Bearer {app_key}"}
    results = {}
    for key in (
        "example-echo-langgraph",
        "example-echo-native",
        "example-echo-runnable",
    ):
        r = await client.post(
            f"/v1/agents/{key}/invoke",
            headers=headers,
            json={"input": "uniform", "stream": False},
        )
        assert r.status_code == 200, f"{key}: {r.text}"
        data = r.json()["data"]
        # 三个共同字段
        assert "session_id" in data
        assert "request_id" in data
        assert "answer" in data
        assert "steps" in data
        results[key] = data

    # 三种范式都成功，answer 各自独立但 schema 统一
    assert results["example-echo-langgraph"]["answer"].startswith("echo: ")
    assert results["example-echo-native"]["answer"].startswith("echo(native): ")
    assert results["example-echo-runnable"]["answer"].startswith("echo(runnable): ")
