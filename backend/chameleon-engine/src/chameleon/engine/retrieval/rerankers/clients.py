"""外部 reranker 模型客户端（BGE / Cohere）—— PR B3

两个 HTTP 客户端，把 (query, documents) 打成相关性分数：

- BgeReranker    —— 自托管 BGE-reranker-v2 服务（Xinference / TEI / Jina 兼容
  的 /rerank 端点）。容忍两种响应形态：
    Cohere 风格 {"results": [{"index", "relevance_score"}]}
    TEI 风格    [{"index", "score"}]
- CohereReranker —— Cohere 官方 /v2/rerank API。

借 RagFlow rag/llm/rerank_model.py 的多客户端思路（每家一个 client，统一
rerank 接口）；不 cp 源码。

红线：HTTP 失败 raise，由 make_client_reranker 兜成"原顺序"（reranker 可选，
不许拖垮主检索）。
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from chameleon.engine.retrieval.hybrid import Hit
from chameleon.engine.retrieval.rerankers.base import (
    Reranker,
    RerankScore,
    apply_rerank_scores,
)

_DEFAULT_TIMEOUT = 30.0
_DEFAULT_BGE_MODEL = "bge-reranker-v2-m3"
_DEFAULT_COHERE_MODEL = "rerank-multilingual-v3.0"
_DEFAULT_COHERE_URL = "https://api.cohere.com/v2/rerank"


def _parse_rerank_response(data: Any) -> list[RerankScore]:
    """容忍 Cohere 风格 {results:[{index, relevance_score}]} 与 TEI 风格 [{index, score}]"""
    rows = data.get("results") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError(f"rerank 响应格式异常: {type(data)}")
    out: list[RerankScore] = []
    for r in rows:
        idx = r.get("index")
        score = r.get("relevance_score")
        if score is None:
            score = r.get("score")
        if idx is None or score is None:
            continue
        out.append(RerankScore(index=int(idx), score=float(score)))
    return out


async def _post_rerank(
    *,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> list[RerankScore]:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        raise RuntimeError(f"rerank request failed: {e}") from e
    if resp.status_code >= 400:
        raise RuntimeError(f"rerank http {resp.status_code}: {resp.text[:300]}")
    return _parse_rerank_response(resp.json())


class BgeReranker:
    """自托管 BGE reranker（/rerank 端点）"""

    name = "bge"

    def __init__(
        self,
        *,
        base_url: str,
        model: str = _DEFAULT_BGE_MODEL,
        api_key: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    async def rerank(
        self, query: str, documents: list[str], *, top_n: int | None = None
    ) -> list[RerankScore]:
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
            # 同时给 documents + texts，兼容 Cohere 风格与 TEI 风格服务
            "documents": documents,
            "texts": documents,
        }
        if top_n:
            payload["top_n"] = top_n
        return await _post_rerank(
            url=url, headers=headers, payload=payload, timeout=self.timeout
        )


class CohereReranker:
    """Cohere 官方 rerank API"""

    name = "cohere"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = _DEFAULT_COHERE_MODEL,
        base_url: str = _DEFAULT_COHERE_URL,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        if not api_key:
            raise ValueError("CohereReranker 需要 api_key")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout

    async def rerank(
        self, query: str, documents: list[str], *, top_n: int | None = None
    ) -> list[RerankScore]:
        if not documents:
            return []
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": top_n or len(documents),
        }
        return await _post_rerank(
            url=self.base_url,
            headers=headers,
            payload=payload,
            timeout=self.timeout,
        )


def make_client_reranker(
    client: BgeReranker | CohereReranker,
    *,
    keep_top_k: int | None = None,
) -> Reranker:
    """把外部模型 client 适配成 HybridPipeline.reranker callable

    失败（HTTP / 解析）→ 退化为原顺序（reranker 不许拖垮主检索）。
    """

    async def reranker(query: str, hits: list[Hit]) -> list[Hit]:
        if not hits:
            return []
        try:
            scores = await client.rerank(
                query, [h.content for h in hits], top_n=keep_top_k
            )
        except Exception:
            logger.exception(
                "reranker {} failed | fallback to original order", client.name
            )
            return hits[:keep_top_k] if keep_top_k else hits
        return apply_rerank_scores(hits, scores, keep_top_k=keep_top_k)

    return reranker
