"""OpenAI / Jina / Cohere 兼容的 rerank 客户端（POST {base_url}/rerank）。

与 OpenAICompatEmbedding 对等，作为 integrations 层的模型客户端。返回中性
`RerankResult`（不依赖 engine 的 RerankScore），engine 检索管线按 .index/.score
鸭子类型适配（make_client_reranker）。

网关模式下 base_url=new-api（统一 /rerank 端点，代理到上游 rerank）；直连模式下
仅对暴露 OpenAI 兼容 /rerank 的供应商有效（DashScope 原生 rerank 不在 /compatible-mode，
故 qwen rerank 实际走网关）。
"""

from __future__ import annotations

from dataclasses import dataclass
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

DEFAULT_TIMEOUT = 30.0


@dataclass
class RerankResult:
    """单条文档重排得分（index 对应传入 documents 下标）—— 鸭子兼容 engine.RerankScore"""

    index: int
    score: float


class OpenAICompatReranker:
    """OpenAI/Jina/Cohere 兼容 rerank 客户端"""

    name = "registry"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        model_code: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        # model = 打给上游的模型名（网关模式下是 upstream_name）；model_code = 逻辑 code
        self.model = model
        self.model_code = model_code or model
        self.timeout = timeout

    async def rerank(
        self, query: str, documents: list[str], *, top_n: int | None = None
    ) -> list[RerankResult]:
        if not documents:
            return []
        url = (
            self.base_url
            if self.base_url.endswith("/rerank")
            else f"{self.base_url}/rerank"
        )
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload: dict[str, Any] = {
            "model": self.model,
            "query": query,
            # 同时给 documents + texts，兼容 Cohere 风格与 TEI/Jina 风格服务
            "documents": documents,
            "texts": documents,
        }
        if top_n:
            payload["top_n"] = top_n

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as e:
            raise ProviderUnreachableError(message=f"rerank timeout: {e}") from e
        except httpx.ConnectError as e:
            raise ProviderUnreachableError(message=f"rerank unreachable: {e}") from e
        except httpx.HTTPError as e:
            raise ProviderInternalError(message=f"rerank http error: {e}") from e

        if resp.status_code >= 400:
            body = resp.text[:500]
            logger.warning("rerank http {} | body={}", resp.status_code, body)
            if resp.status_code in (401, 403):
                raise ProviderAuthError(message=f"rerank auth failed: {body}")
            if resp.status_code == 429:
                raise ProviderRateLimitError(message="rerank rate limit")
            if 400 <= resp.status_code < 500:
                raise ProviderInputError(message=f"rerank rejected: {body}")
            raise ProviderInternalError(
                message=f"rerank http {resp.status_code}: {body}"
            )

        return _parse_rerank_response(resp.json())


def _parse_rerank_response(data: Any) -> list[RerankResult]:
    """容忍 Cohere/Jina（results）与部分服务（data）两种形态。"""
    items = data.get("results") or data.get("data") or []
    out: list[RerankResult] = []
    for it in items:
        idx = it.get("index")
        score = it.get("relevance_score")
        if score is None:
            score = it.get("score")
        if idx is None or score is None:
            continue
        out.append(RerankResult(index=int(idx), score=float(score)))
    return out
