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
    msg = (body.get("params") or {}).get("message") or {}
    text = _parts_text(msg.get("parts"))
    # 复用 dev_call_agent：stream 聚合 + durable HITL（pending）
    out = await service.dev_call_agent(target=key, input=text)
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
