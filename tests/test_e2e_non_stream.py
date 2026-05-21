"""Phase 3 端到端非流冒烟（注：流式在 Phase 4 加）

链路：admin key → 发 app key → 调 mock-echo agent → 验 session/messages/call_logs
"""

from httpx import AsyncClient


async def test_health(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200


async def test_admin_create_app_key(client: AsyncClient, admin_key: str) -> None:
    r = await client.post(
        "/v1/admin/api-keys",
        headers={"Authorization": f"Bearer {admin_key}"},
        json={"app_id": "e2e-app-from-admin", "name": "via-admin", "scopes": []},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"]
    plain = body["data"]["plain_key"]
    assert plain.startswith("chm_")
    assert body["data"]["scopes"] == []


async def test_app_key_cannot_access_admin(client: AsyncClient, app_key: str) -> None:
    """普通 app key 不能访问 admin 接口"""
    r = await client.get(
        "/v1/admin/api-keys",
        headers={"Authorization": f"Bearer {app_key}"},
    )
    body = r.json()
    assert body["success"] is False
    assert body["code"] == 40301  # AdminScopeRequired
    assert r.status_code == 403


async def test_list_agents(client: AsyncClient, app_key: str) -> None:
    r = await client.get(
        "/v1/agents",
        headers={"Authorization": f"Bearer {app_key}"},
    )
    assert r.status_code == 200
    keys = {a["key"] for a in r.json()["data"]}
    assert "mock-echo" in keys


async def test_invoke_non_stream_str_input(client: AsyncClient, app_key: str) -> None:
    """str input → 自动签发 session + history 走 PG"""
    r = await client.post(
        "/v1/agents/mock-echo/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={"input": "hello", "stream": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"]
    data = body["data"]
    assert data["session_id"].startswith("sess_")
    assert data["answer"] == "echo: hello"
    assert any(s["name"] == "intent_route" for s in data["steps"])
    assert data["usage"]["total_tokens"] == 8


async def test_invoke_multi_turn_history_replay(
    client: AsyncClient, app_key: str
) -> None:
    """第二轮带 session_id；mock provider 看到的 input 仍是本轮（不验证 history 内容，
    但通过 listing /messages 验证两轮都落库）"""
    headers = {"Authorization": f"Bearer {app_key}"}

    r1 = await client.post(
        "/v1/agents/mock-echo/invoke",
        headers=headers,
        json={"input": "round1", "stream": False},
    )
    sid = r1.json()["data"]["session_id"]

    r2 = await client.post(
        "/v1/agents/mock-echo/invoke",
        headers=headers,
        json={"input": "round2", "session_id": sid, "stream": False},
    )
    assert r2.json()["data"]["session_id"] == sid
    assert r2.json()["data"]["answer"] == "echo: round2"

    msgs = await client.get(
        f"/v1/conversations/{sid}/messages",
        headers=headers,
    )
    items = msgs.json()["data"]["items"]
    contents = [m["content"] for m in items]
    # 应该是 [user:round1, assistant:echo: round1, user:round2, assistant:echo: round2]
    assert contents == ["round1", "echo: round1", "round2", "echo: round2"]


async def test_invoke_list_messages_input_no_session_history(
    client: AsyncClient, app_key: str
) -> None:
    """list[Message] 模式：不消费 session 历史，但当前轮 user msg 仍落库"""
    headers = {"Authorization": f"Bearer {app_key}"}

    # 先建一轮制造历史
    r1 = await client.post(
        "/v1/agents/mock-echo/invoke",
        headers=headers,
        json={"input": "前置消息", "stream": False},
    )
    sid = r1.json()["data"]["session_id"]

    # 用 list 形式调，应不消费 session 历史
    r2 = await client.post(
        "/v1/agents/mock-echo/invoke",
        headers=headers,
        json={
            "input": [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "嗨"},
                {"role": "user", "content": "今天天气如何"},
            ],
            "session_id": sid,
            "stream": False,
        },
    )
    body = r2.json()
    assert body["success"]
    assert body["data"]["answer"] == "echo: 今天天气如何"

    # 验证只有最后一条 user 落库了（A10 裁决）
    msgs = await client.get(
        f"/v1/conversations/{sid}/messages",
        headers=headers,
    )
    items = msgs.json()["data"]["items"]
    contents = [m["content"] for m in items]
    # 应该是 [前置 user, 前置 assistant, 第二轮 user(最后一条), 第二轮 assistant]
    assert contents == [
        "前置消息",
        "echo: 前置消息",
        "今天天气如何",
        "echo: 今天天气如何",
    ]


async def test_conversation_not_found(client: AsyncClient, app_key: str) -> None:
    r = await client.get(
        "/v1/conversations/sess_nonexistent",
        headers={"Authorization": f"Bearer {app_key}"},
    )
    assert r.status_code == 404
    assert r.json()["code"] == 40402


async def test_cross_app_session_isolation(client: AsyncClient) -> None:
    """app A 的 session app B 看不到（表现为 NotFound，不泄漏存在性）"""
    import secrets

    from chameleon.app.modules.api_key.schemas import CreateApiKeyRequest
    from chameleon.app.modules.api_key.service import create_api_key
    from chameleon.core.infra.db import AsyncSessionLocal

    rand = secrets.token_hex(3)
    async with AsyncSessionLocal() as s:
        a_key_obj = await create_api_key(
            s,
            CreateApiKeyRequest(app_id=f"e2e-iso-a-{rand}", name="A", scopes=[]),
        )
        b_key_obj = await create_api_key(
            s,
            CreateApiKeyRequest(app_id=f"e2e-iso-b-{rand}", name="B", scopes=[]),
        )
        await s.commit()
    a_key, b_key = a_key_obj.plain_key, b_key_obj.plain_key

    r = await client.post(
        "/v1/agents/mock-echo/invoke",
        headers={"Authorization": f"Bearer {a_key}"},
        json={"input": "from A", "stream": False},
    )
    sid = r.json()["data"]["session_id"]

    r_b = await client.get(
        f"/v1/conversations/{sid}",
        headers={"Authorization": f"Bearer {b_key}"},
    )
    assert r_b.status_code == 404
    assert r_b.json()["code"] == 40402


async def test_admin_call_logs_filter(
    client: AsyncClient, admin_key: str, app_key: str
) -> None:
    """触发一次调用 → admin 能在 call_logs 看到，且按 app_id / success 过滤"""
    headers_app = {"Authorization": f"Bearer {app_key}"}
    headers_admin = {"Authorization": f"Bearer {admin_key}"}

    invoke_resp = await client.post(
        "/v1/agents/mock-echo/invoke",
        headers=headers_app,
        json={"input": "trace this", "stream": False},
    )
    rid = invoke_resp.json()["data"]["request_id"]

    logs = await client.get(
        "/v1/admin/call-logs?success=true",
        headers=headers_admin,
    )
    items = logs.json()["data"]["items"]
    assert any(log["request_id"] == rid for log in items)
    assert all(log["success"] for log in items)


async def test_session_agent_mismatch_rejected(
    client: AsyncClient, app_key: str
) -> None:
    """同一 session 不能跨 agent 调用"""
    # 注入第二个 mock agent
    from chameleon.providers.base import AGENTS
    from chameleon.providers.base.types import AgentDef

    AGENTS["mock-echo-2"] = AgentDef(
        key="mock-echo-2",
        provider="mock",
        description="second mock for cross-agent test",
    )
    try:
        headers = {"Authorization": f"Bearer {app_key}"}
        r1 = await client.post(
            "/v1/agents/mock-echo/invoke",
            headers=headers,
            json={"input": "a", "stream": False},
        )
        sid = r1.json()["data"]["session_id"]

        r2 = await client.post(
            "/v1/agents/mock-echo-2/invoke",
            headers=headers,
            json={"input": "b", "session_id": sid, "stream": False},
        )
        body = r2.json()
        assert body["success"] is False
        assert body["code"] == 40010
    finally:
        AGENTS.pop("mock-echo-2", None)
