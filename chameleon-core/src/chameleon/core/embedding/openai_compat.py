"""OpenAI 兼容协议 embedding 客户端

适配：OpenAI / DeepSeek / Qwen 兼容模式 / vLLM 等。
端点：POST {base_url}/embeddings
"""

from __future__ import annotations

import httpx
from loguru import logger

from chameleon.core.exceptions import (
    ProviderAuthError,
    ProviderInputError,
    ProviderInternalError,
    ProviderRateLimitError,
    ProviderUnreachableError,
)

DEFAULT_TIMEOUT = 60.0
_BATCH_SIZE_MAX = 64  # 单次请求最多 64 条文本（OpenAI 上限 2048，但低也无碍）


class OpenAICompatEmbedding:
    """OpenAI 兼容 embedding 客户端"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dim: int,
        timeout: float = DEFAULT_TIMEOUT,
        batch_size: int = _BATCH_SIZE_MAX,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dim = dim
        self.timeout = timeout
        self.batch_size = min(batch_size, _BATCH_SIZE_MAX)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            results.extend(await self._embed_batch(batch))
        return results

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.model, "input": batch}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as e:
            raise ProviderUnreachableError(message=f"embedding timeout: {e}") from e
        except httpx.ConnectError as e:
            raise ProviderUnreachableError(message=f"embedding unreachable: {e}") from e
        except httpx.HTTPError as e:
            raise ProviderInternalError(message=f"embedding http error: {e}") from e

        if resp.status_code >= 400:
            body = resp.text[:500]
            logger.warning("embedding http {} | body={}", resp.status_code, body)
            if resp.status_code in (401, 403):
                raise ProviderAuthError(message=f"embedding auth failed: {body}")
            if resp.status_code == 429:
                raise ProviderRateLimitError(message="embedding rate limit")
            if 400 <= resp.status_code < 500:
                raise ProviderInputError(message=f"embedding rejected: {body}")
            raise ProviderInternalError(
                message=f"embedding http {resp.status_code}: {body}"
            )

        data = resp.json()
        items = data.get("data") or []
        vectors = [item["embedding"] for item in items]
        if len(vectors) != len(batch):
            raise ProviderInternalError(
                message=f"embedding length mismatch: expected {len(batch)}, got {len(vectors)}"
            )
        if vectors and len(vectors[0]) != self.dim:
            raise ProviderInternalError(
                message=(
                    f"embedding dim mismatch: configured {self.dim}, "
                    f"actual {len(vectors[0])}"
                )
            )
        return vectors
