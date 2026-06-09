"""A2A 协议出站客户端（开放 A2A Slice A）——调用**远程** Agent2Agent 智能体。

对齐 Google Agent2Agent 规范：AgentCard（`/.well-known/agent.json`）做能力发现，JSON-RPC
`message/send` 发消息、解析返回的 task/message 取文本。供 ctx.call_agent 的 URL 路由（Slice A.2）
调用——target 是 http(s) URL 时走这里调远程 agent，进程内 key 仍走 a2a_bridge 进程内 caller。

红线（见子方案 §4）：远程 agent 上报的 token/budget 不可信（本地按往返计费）；远程输出当
untrusted；trace_id 经 metadata 透传。
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx

_WELL_KNOWN = "/.well-known/agent.json"


class A2AError(RuntimeError):
    """远程 A2A 调用失败（网络 / JSON-RPC error / task failed）。"""


def _parts_text(parts: list[dict[str, Any]] | None) -> str:
    """从 A2A message/artifact 的 parts 抽文本（kind=='text' 的 part 拼接）。"""
    return "".join(p.get("text", "") for p in (parts or []) if p.get("kind") == "text")


class A2AClient:
    """单个远程 A2A agent 的客户端。`base_url` 为 agent 根（AgentCard 在其 /.well-known 下）。"""

    def __init__(
        self,
        base_url: str,
        *,
        http: httpx.AsyncClient | None = None,
        timeout: float = 60.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._http = http
        self._timeout = timeout
        self._headers = headers or {}

    async def _client(self) -> tuple[httpx.AsyncClient, bool]:
        if self._http is not None:
            return self._http, False
        return httpx.AsyncClient(timeout=self._timeout, headers=self._headers), True

    async def agent_card(self) -> dict[str, Any]:
        """拉取 AgentCard（能力发现）。"""
        client, owned = await self._client()
        try:
            r = await client.get(f"{self._base}{_WELL_KNOWN}")
            r.raise_for_status()
            return r.json()
        finally:
            if owned:
                await client.aclose()

    async def call(self, text: str, *, trace_id: str | None = None, depth: int = 0) -> str:
        """JSON-RPC message/send 发一条用户消息，返回远程 agent 的文本答案（同步等终态）。

        `depth`：A2A 调用深度，经 message.metadata 透传——远程若是本系统 /a2a 入站，会读它续计
        深度而非重置成 0，防跨系统 A2A 环无限递归（评审19 #3）。
        """
        metadata: dict[str, Any] = {}
        if trace_id:
            metadata["trace_id"] = trace_id
        if depth:
            metadata["a2a_depth"] = depth
        rpc = {
            "jsonrpc": "2.0",
            "id": uuid.uuid4().hex,
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": text}],
                    "messageId": uuid.uuid4().hex,
                    **({"metadata": metadata} if metadata else {}),
                }
            },
        }
        client, owned = await self._client()
        try:
            r = await client.post(self._base, json=rpc)
            r.raise_for_status()
            body = r.json()
        except (httpx.HTTPError, ValueError) as e:  # 网络/4xx/5xx/非 JSON → 统一 A2AError（评审19 #5）
            raise A2AError(f"远程 A2A 调用失败：{type(e).__name__}: {e}") from e
        finally:
            if owned:
                await client.aclose()
        if "error" in body:
            raise A2AError(f"远程 A2A JSON-RPC error: {body['error']}")
        result = body.get("result") or {}
        return _extract_answer(result)


def _extract_answer(result: dict[str, Any]) -> str:
    """从 message/send 的 result（Message 或 Task）抽最终文本答案。"""
    kind = result.get("kind")
    if kind == "message":  # 直接消息回复
        return _parts_text(result.get("parts"))
    # Task：终态须 completed；取 artifacts 文本，回退 status.message
    status = result.get("status") or {}
    state = status.get("state")
    if state == "failed":
        raise A2AError(f"远程 A2A task failed: {status.get('message')}")
    if state == "input-required":
        # HITL：远程 agent 暂停等输入。Slice A（只读）不处理续跑，明确报错（Slice C 接 durable）。
        raise A2AError("远程 A2A task 进入 input-required（需 HITL 续跑，Slice C 支持）")
    artifacts = result.get("artifacts") or []
    text = "".join(_parts_text(a.get("parts")) for a in artifacts)
    if text:
        return text
    # 回退：status.message 的 parts
    msg = status.get("message") or {}
    return _parts_text(msg.get("parts"))
