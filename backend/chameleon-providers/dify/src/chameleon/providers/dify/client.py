"""DIFY HTTP 客户端封装

仅 stream（流式）模式：所有 invoke 都走 SSE，非流由 provider 默认聚合。
端点：
  /chat-messages       —— mode=chat
  /workflows/run       —— mode=workflow
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from loguru import logger

from chameleon.core.api.exceptions import (
    ProviderAuthError,
    ProviderInputError,
    ProviderInternalError,
    ProviderRateLimitError,
    ProviderUnreachableError,
)

DEFAULT_TIMEOUT = 60.0


class DifyClient:
    def __init__(
        self,
        endpoint: str,
        api_key: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

    async def stream_chat(
        self,
        *,
        query: str,
        conversation_id: str | None,
        user: str,
        inputs: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """POST /chat-messages，streaming mode

        Yields: 每个 SSE event 解析后的 dict（含 event/data 字段）
        """
        payload = {
            "query": query,
            "inputs": inputs or {},
            "response_mode": "streaming",
            "user": user,
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id

        url = f"{self.endpoint}/chat-messages"
        async for chunk in self._sse_request(url, payload):
            yield chunk

    async def stream_workflow(
        self,
        *,
        inputs: dict[str, Any],
        user: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """POST /workflows/run，streaming mode（workflow 不支持 conversation_id）"""
        payload = {
            "inputs": inputs,
            "response_mode": "streaming",
            "user": user,
        }
        url = f"{self.endpoint}/workflows/run"
        async for chunk in self._sse_request(url, payload):
            yield chunk

    async def _sse_request(
        self, url: str, payload: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST", url, headers=self._headers(), json=payload
                ) as resp:
                    if resp.status_code >= 400:
                        await self._raise_http_error(resp)
                    async for line in resp.aiter_lines():
                        ev = _parse_sse_line(line)
                        if ev is not None:
                            yield ev
        except httpx.TimeoutException as e:
            raise ProviderUnreachableError(message=f"dify timeout: {e}") from e
        except httpx.ConnectError as e:
            raise ProviderUnreachableError(message=f"dify unreachable: {e}") from e
        except httpx.HTTPError as e:
            raise ProviderInternalError(message=f"dify http error: {e}") from e

    async def _raise_http_error(self, resp: httpx.Response) -> None:
        body = await resp.aread()
        text = body.decode("utf-8", errors="replace")
        logger.warning("dify http {} | body={}", resp.status_code, text[:500])
        if resp.status_code in (401, 403):
            raise ProviderAuthError(message=f"dify auth failed: {text[:200]}")
        if resp.status_code == 429:
            raise ProviderRateLimitError(message="dify rate limit exceeded")
        if 400 <= resp.status_code < 500:
            raise ProviderInputError(message=f"dify rejected request: {text[:200]}")
        raise ProviderInternalError(message=f"dify {resp.status_code}: {text[:200]}")


# ── SSE 行解析 ──────────────────────────────────────────


def _parse_sse_line(line: str) -> dict[str, Any] | None:
    """DIFY SSE 行格式：
       data: {"event":"message","conversation_id":"...","answer":"..."}

    每个 event 一行（与标准 SSE 同），data: 前缀剥掉后是 JSON。
    """
    if not line or not line.startswith("data:"):
        return None
    payload = line[len("data:") :].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("dify sse non-json line: {}", payload[:200])
        return None
