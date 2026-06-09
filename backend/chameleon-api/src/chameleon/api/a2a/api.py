"""入站开放 A2A（Slice B）：把自家 agent 暴露成标准 Agent2Agent 端点。

- `GET /a2a/{key}/.well-known/agent.json`：AgentCard（能力发现，从 registry 合成）。
- `POST /a2a/{key}`：JSON-RPC `message/send` → 调 agent → 映射成 A2A task。

复用 dev_call_agent（stream 聚合 + durable HITL）：agent ctx.ask_human 暂停 → dev_call_agent 返
pending → 映射成 A2A `input-required`（子方案的 durable↔A2A 协同：A2A input-required == ask_human）。
dev-token 鉴权（与 /mcp、/v1/dev/* 同一 opt-in 闸）；生产 api_key scope 见 Slice D。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from chameleon.api.dev import service
from chameleon.api.dev.api import require_dev_token

router = APIRouter(prefix="/a2a", tags=["a2a"])

#: A2A 跨系统深度上限（评审19 #3）——入站读 message.metadata.a2a_depth，超限拒，防 A2A 环递归。
_A2A_MAX_DEPTH = 5


def _parts_text(parts: list[dict[str, Any]] | None) -> str:
    return "".join(p.get("text", "") for p in (parts or []) if p.get("kind") == "text")


@router.get("/{key}/.well-known/agent.json")
async def agent_card(key: str, _: None = Depends(require_dev_token)) -> dict[str, Any]:
    from chameleon.providers.base import AGENTS

    adef = AGENTS.get(key)
    if adef is None:
        raise HTTPException(status_code=404, detail=f"agent 不存在: {key}")
    desc = adef.description or f"Chameleon agent {key}"
    return {
        "name": key,
        "description": desc,
        "url": f"/a2a/{key}",
        "version": adef.version or "0.1.0",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [{"id": key, "name": key, "description": desc, "tags": list(adef.tags or [])}],
    }


@router.post("/{key}")
async def message_send(
    key: str, body: dict[str, Any], _: None = Depends(require_dev_token)
) -> dict[str, Any]:
    rpc_id = body.get("id")
    if body.get("method") != "message/send":
        return {"jsonrpc": "2.0", "id": rpc_id,
                "error": {"code": -32601, "message": f"unsupported method: {body.get('method')}"}}
    params = body.get("params")
    msg = params.get("message") if isinstance(params, dict) else None
    if not isinstance(msg, dict):  # 畸形 params/message → Invalid params（评审19 #5：非 500）
        return {"jsonrpc": "2.0", "id": rpc_id,
                "error": {"code": -32602, "message": "invalid params: message 缺失或非对象"}}
    text = _parts_text(msg.get("parts"))
    if not text.strip():  # 空消息短路拒，别真跑模型烧 token（评审19 #5 滥用面）
        return {"jsonrpc": "2.0", "id": rpc_id,
                "error": {"code": -32602, "message": "invalid params: 消息文本为空"}}
    # 跨系统深度续计：读 message.metadata.a2a_depth（出站客户端透传），超限拒（评审19 #3）
    depth = int((msg.get("metadata") or {}).get("a2a_depth") or 0)
    if depth > _A2A_MAX_DEPTH:
        return {"jsonrpc": "2.0", "id": rpc_id,
                "error": {"code": -32000, "message": f"A2A 深度超限（>{_A2A_MAX_DEPTH}）：防跨系统环"}}
    # 复用 dev_call_agent：stream 聚合 + durable HITL（pending）；透传深度不重置
    out = await service.dev_call_agent(target=key, input=text, a2a_depth=depth)
    if out.get("error"):
        return {"jsonrpc": "2.0", "id": rpc_id,
                "error": {"code": -32000, "message": out["error"]}}
    if out.get("pending"):  # durable HITL 暂停 → A2A input-required（远程调用方回填后续 task）
        p = out["pending"]
        return {"jsonrpc": "2.0", "id": rpc_id, "result": {
            "kind": "task", "id": out.get("run_id"),
            "status": {"state": "input-required",
                       "message": {"role": "agent",
                                   "parts": [{"kind": "text", "text": p.get("prompt", "")}]}},
        }}
    return {"jsonrpc": "2.0", "id": rpc_id, "result": {
        "kind": "task", "id": out.get("run_id"), "status": {"state": "completed"},
        "artifacts": [{"parts": [{"kind": "text", "text": out.get("answer", "")}]}],
    }}
