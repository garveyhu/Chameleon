"""入站开放 A2A（Slice B）：/a2a/{key} AgentCard + message/send（JSON-RPC）映射成 A2A task。
TestClient 跑路由；mock AGENTS（免真 registry）+ dev_call_agent（免真模型）。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from chameleon.api.a2a import a2a_router
from chameleon.api.a2a import api as a2a_api
from chameleon.api.dev.api import require_dev_token


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(a2a_router)
    app.dependency_overrides[require_dev_token] = lambda: None
    fake = SimpleNamespace(key="qwen-chat", description="测试 agent", version="1.2", tags=["x"])
    monkeypatch.setattr("chameleon.providers.base.AGENTS", {"qwen-chat": fake})
    return TestClient(app)


def test_agent_card(client):
    r = client.get("/a2a/qwen-chat/.well-known/agent.json")
    assert r.status_code == 200
    card = r.json()
    assert card["name"] == "qwen-chat" and card["description"] == "测试 agent"
    assert card["version"] == "1.2"
    # 评审20 #8：url 绝对（外部 A2A 客户端可直接 POST）+ A2A spec 必填字段
    assert card["url"].startswith("http") and card["url"].endswith("/a2a/qwen-chat")
    assert card["protocolVersion"] == "0.2.0" and card["preferredTransport"] == "JSONRPC"
    assert card["defaultInputModes"] == ["text"] and card["skills"][0]["id"] == "qwen-chat"


def test_agent_card_404(client):
    assert client.get("/a2a/nope/.well-known/agent.json").status_code == 404


def test_message_send_completed(client, monkeypatch):
    async def _fake(*, target, input, **kw):
        return {"answer": f"答:{input}", "run_id": "r1"}

    monkeypatch.setattr(a2a_api.service, "dev_call_agent", _fake)
    r = client.post("/a2a/qwen-chat", json={
        "jsonrpc": "2.0", "id": "1", "method": "message/send",
        "params": {"message": {"role": "user", "parts": [{"kind": "text", "text": "你好"}]}},
    })
    body = r.json()
    result = body["result"]
    assert result["kind"] == "task" and result["status"]["state"] == "completed"
    assert result["artifacts"][0]["parts"][0]["text"] == "答:你好"


def test_message_send_pending_maps_to_input_required(client, monkeypatch):
    """durable HITL 暂停 → A2A input-required（子方案的 durable↔A2A 协同）。"""
    async def _fake(*, target, input, **kw):
        return {"answer": "", "run_id": "r2", "pending": {"call_index": 1, "prompt": "批准吗？"}}

    monkeypatch.setattr(a2a_api.service, "dev_call_agent", _fake)
    r = client.post("/a2a/qwen-chat", json={
        "jsonrpc": "2.0", "id": "2", "method": "message/send",
        "params": {"message": {"parts": [{"kind": "text", "text": "删库"}]}},
    })
    result = r.json()["result"]
    assert result["status"]["state"] == "input-required"
    assert result["status"]["message"]["parts"][0]["text"] == "批准吗？"


def test_unsupported_method_jsonrpc_error(client):
    r = client.post("/a2a/qwen-chat", json={"jsonrpc": "2.0", "id": "3", "method": "tasks/cancel"})
    err = r.json()["error"]
    assert err["code"] == -32601 and "unsupported" in err["message"]


def test_malformed_params_returns_invalid_params_not_500(client):
    """评审19 #5：params 非 dict / message 缺失 → -32602 Invalid params（非不透明 500）。"""
    for params in ("不是对象", None, {"message": "也不是对象"}):
        r = client.post("/a2a/qwen-chat",
                        json={"jsonrpc": "2.0", "id": "x", "method": "message/send", "params": params})
        assert r.status_code == 200 and r.json()["error"]["code"] == -32602


def test_empty_message_rejected_no_model_burn(client, monkeypatch):
    """评审19 #5：空消息文本短路拒，不真跑模型烧 token。"""
    called = {"n": 0}

    async def _fake(*, target, input, **kw):
        called["n"] += 1
        return {"answer": "x", "run_id": "r"}

    monkeypatch.setattr(a2a_api.service, "dev_call_agent", _fake)
    r = client.post("/a2a/qwen-chat", json={
        "jsonrpc": "2.0", "id": "x", "method": "message/send",
        "params": {"message": {"parts": [{"kind": "text", "text": "   "}]}},
    })
    assert r.json()["error"]["code"] == -32602
    assert called["n"] == 0  # 没调到 agent / 模型


def test_inbound_depth_cap(client):
    """评审19 #3：入站读 message.metadata.a2a_depth 超限拒，防跨系统 A2A 环。"""
    r = client.post("/a2a/qwen-chat", json={
        "jsonrpc": "2.0", "id": "x", "method": "message/send",
        "params": {"message": {"parts": [{"kind": "text", "text": "q"}],
                               "metadata": {"a2a_depth": 6}}},
    })
    assert "深度超限" in r.json()["error"]["message"]


def test_inbound_hitl_resume_via_task_id(client, monkeypatch):
    """Slice C：message 带 taskId（暂停 task 的 run_id）→ 路由到 dev_call_agent resume
    （run_id=taskId + resume_answer=文本，call_index 服务端读）→ 续跑完成。"""
    seen = {}

    async def _fake(*, target, input, run_id=None, resume_answer=None, **kw):
        seen.update(run_id=run_id, resume_answer=resume_answer)
        return {"answer": f"续跑:{resume_answer}", "run_id": run_id}

    monkeypatch.setattr(a2a_api.service, "dev_call_agent", _fake)
    r = client.post("/a2a/qwen-chat", json={
        "jsonrpc": "2.0", "id": "x", "method": "message/send",
        "params": {"message": {"taskId": "task-1", "parts": [{"kind": "text", "text": "同意"}]}},
    })
    assert seen["run_id"] == "task-1" and seen["resume_answer"] == "同意"
    result = r.json()["result"]
    assert result["status"]["state"] == "completed"
    assert result["artifacts"][0]["parts"][0]["text"] == "续跑:同意"


def test_inbound_propagates_depth(client, monkeypatch):
    """入站把 metadata.a2a_depth 透传给 dev_call_agent（不重置 0），续计跨系统深度。"""
    seen = {}

    async def _fake(*, target, input, a2a_depth=0, **kw):
        seen["depth"] = a2a_depth
        return {"answer": "ok", "run_id": "r"}

    monkeypatch.setattr(a2a_api.service, "dev_call_agent", _fake)
    client.post("/a2a/qwen-chat", json={
        "jsonrpc": "2.0", "id": "x", "method": "message/send",
        "params": {"message": {"parts": [{"kind": "text", "text": "q"}],
                               "metadata": {"a2a_depth": 3}}},
    })
    assert seen["depth"] == 3
