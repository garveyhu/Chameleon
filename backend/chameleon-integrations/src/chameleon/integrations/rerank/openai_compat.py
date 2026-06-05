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
        # DashScope 原生 rerank 不在 /compatible-mode，单独走原生端点 →
        # 直连 qwen（不引入 new-api）也能用；其余走 OpenAI/Jina/Cohere 兼容 /rerank。
        if "dashscope.aliyuncs.com" in self.base_url:
            return await self._rerank_dashscope(query, documents, top_n)
        return await self._rerank_compat(query, documents, top_n)

    async def _rerank_compat(
        self, query: str, documents: list[str], top_n: int | None
    ) -> list[RerankResult]:
        url = (
            self.base_url
            if self.base_url.endswith("/rerank")
            else f"{self.base_url}/rerank"
        )
        payload: dict[str, Any] = {
            "model": self.model,
            "query": query,
            # 同时给 documents + texts，兼容 Cohere 风格与 TEI/Jina 风格服务
            "documents": documents,
            "texts": documents,
        }
        if top_n:
            payload["top_n"] = top_n
        data = await self._post(url, payload)
        return _to_results(data.get("results") or data.get("data") or [])

    async def _rerank_dashscope(
        self, query: str, documents: list[str], top_n: int | None
    ) -> list[RerankResult]:
        from urllib.parse import urlparse

        parsed = urlparse(self.base_url)
        url = (
            f"{parsed.scheme}://{parsed.netloc}"
            "/api/v1/services/rerank/text-rerank/text-rerank"
        )
        parameters: dict[str, Any] = {"return_documents": False}
        if top_n:
            parameters["top_n"] = top_n
        payload = {
            "model": self.model,
            "input": {"query": query, "documents": documents},
            "parameters": parameters,
        }
        data = await self._post(url, payload)
        return _to_results((data.get("output") or {}).get("results") or [])

    async def _post(self, url: str, payload: dict[str, Any]) -> Any:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
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
        return resp.json()


def _to_results(items: list[dict[str, Any]]) -> list[RerankResult]:
    """归一化 Cohere/Jina（results）/ data / DashScope（output.results）条目。"""
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
