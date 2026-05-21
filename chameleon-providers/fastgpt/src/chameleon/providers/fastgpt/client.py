"""FastGPT HTTP 客户端封装

FastGPT 走 OpenAI 兼容协议：POST /v1/chat/completions
SSE 解析与 OpenAI 一致 + responseData 扩展字段携带 flow node 信息。
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


class FastGPTClient:
    def __init__(
        self, endpoint: str, api_key: str, *, timeout: float = DEFAULT_TIMEOUT
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
        messages: list[dict[str, Any]],
        chat_id: str | None,
        variables: dict[str, Any] | None = None,
        detail: bool = True,
    ) -> AsyncIterator[dict[str, Any]]:
        """POST /v1/chat/completions，stream=true

        Yields: 每个 SSE event 解析后的 dict
        """
        payload: dict[str, Any] = {
            "messages": messages,
            "stream": True,
            "detail": detail,  # 返 responseData 扩展
        }
        if chat_id:
            payload["chatId"] = chat_id
        if variables:
            payload["variables"] = variables

        url = f"{self.endpoint}/v1/chat/completions"
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
                    current_event: str | None = None
                    async for line in resp.aiter_lines():
                        if line.startswith("event:"):
                            current_event = line[len("event:") :].strip()
                            continue
                        if line.startswith("data:"):
                            payload_str = line[len("data:") :].strip()
                            if payload_str == "[DONE]" or not payload_str:
                                current_event = None
                                continue
                            try:
                                obj = json.loads(payload_str)
                            except json.JSONDecodeError:
                                logger.warning(
                                    "fastgpt sse non-json: {}", payload_str[:200]
                                )
                                current_event = None
                                continue
                            # 附上 event name（用于区分 answer chunk vs responseData）
                            yield {"event": current_event or "answer", "data": obj}
                            current_event = None
                            continue
                        if not line:
                            # 空行 → event 分隔
                            current_event = None
        except httpx.TimeoutException as e:
            raise ProviderUnreachableError(message=f"fastgpt timeout: {e}") from e
        except httpx.ConnectError as e:
            raise ProviderUnreachableError(message=f"fastgpt unreachable: {e}") from e
        except httpx.HTTPError as e:
            raise ProviderInternalError(message=f"fastgpt http error: {e}") from e

    async def _raise_http_error(self, resp: httpx.Response) -> None:
        body = await resp.aread()
        text = body.decode("utf-8", errors="replace")
        logger.warning("fastgpt http {} | body={}", resp.status_code, text[:500])
        if resp.status_code in (401, 403):
            raise ProviderAuthError(message=f"fastgpt auth failed: {text[:200]}")
        if resp.status_code == 429:
            raise ProviderRateLimitError(message="fastgpt rate limit exceeded")
        if 400 <= resp.status_code < 500:
            raise ProviderInputError(message=f"fastgpt rejected: {text[:200]}")
        raise ProviderInternalError(message=f"fastgpt {resp.status_code}: {text[:200]}")
