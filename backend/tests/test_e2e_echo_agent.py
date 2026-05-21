"""Phase 6 端到端：echo agent 通过统一 invoke 调通

echo agent 是真实的 LangGraph + EchoChatModel（按字符流），
验证 step / delta / done 全路径。
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


# ── 非流式 ─────────────────────────────────────────────


async def test_echo_invoke_non_stream(client: AsyncClient, app_key: str) -> None:
    r = await client.post(
        "/v1/agents/example-echo-langgraph/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={"input": "hello", "stream": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"]
    data = body["data"]
    assert data["answer"] == "echo: hello"
    # 至少应有 step 事件（route + respond 节点完成）
    assert len(data["steps"]) >= 2
    step_names = {s["name"] for s in data["steps"]}
    assert "route" in step_names or "respond" in step_names


async def test_echo_listed_in_agents(client: AsyncClient, app_key: str) -> None:
    r = await client.get("/v1/agents", headers={"Authorization": f"Bearer {app_key}"})
    items = r.json()["data"]
    echo = next((a for a in items if a["key"] == "example-echo-langgraph"), None)
    assert echo is not None
    assert echo["provider"] == "local"
    assert "example" in echo["tags"]


# ── 流式 ───────────────────────────────────────────────


async def test_echo_invoke_stream(stream_client: AsyncClient, app_key: str) -> None:
    """流式：应收到 delta（按 chunk）+ step + done"""
    async with stream_client.stream(
        "POST",
        "/v1/agents/example-echo-langgraph/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={"input": "hi there", "stream": True},
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join([c async for c in r.aiter_text()])

    events = _parse_sse(body)
    types_seen = {e["event"] for e in events}
    assert "delta" in types_seen
    assert "step" in types_seen
    assert "done" in types_seen
    assert "error" not in types_seen

    delta_text = "".join(e["data"]["text"] for e in events if e["event"] == "delta")
    assert delta_text == "echo: hi there"

    done = next(e for e in events if e["event"] == "done")
    assert done["data"]["answer"] == "echo: hi there"
    assert done["data"]["session_id"].startswith("sess_")


# ── RAG 路径（input 含 doc:<kb_key>） ─────────────────────


async def test_echo_with_rag_doc_marker(client: AsyncClient, app_key: str) -> None:
    """input 含 "doc:<kb_key>" → echo agent 自动 RAG 检索

    验证 in-process search_kb 被 agent 调通。
    """
    headers = {"Authorization": f"Bearer {app_key}"}

    # 准备 KB + ingest
    await client.post(
        "/v1/knowledge",
        headers=headers,
        json={"kb_key": "e2e-echo-rag", "name": "echo rag kb", "chunk_size": 30},
    )
    r = await client.post(
        "/v1/knowledge/e2e-echo-rag/documents",
        headers=headers,
        json={
            "title": "x",
            "source_type": "text",
            "content": "Chameleon 是一个 AI 中枢。",
        },
    )
    task_id = r.json()["data"]["task_id"]

    # 等 task 完成
    for _ in range(50):
        await asyncio.sleep(0.05)
        rs = await client.get(f"/v1/tasks/{task_id}", headers=headers)
        if rs.json()["data"]["status"] == "success":
            break
    else:
        raise AssertionError("ingest task did not finish in time")

    # 调 echo agent，input 含 doc:e2e-echo-rag
    r = await client.post(
        "/v1/agents/example-echo-langgraph/invoke",
        headers=headers,
        json={
            "input": "Chameleon 是什么？ doc:e2e-echo-rag",
            "stream": False,
        },
    )
    body = r.json()
    assert body["success"]
    data = body["data"]
    # answer 仍是 echo prefix
    assert data["answer"].startswith("echo: ")
    # citations 应被填充（mock embedding 同文本同向量 → 至少 1 命中）
    assert len(data["citations"]) >= 1
    assert "Chameleon" in data["citations"][0]["snippet"]
