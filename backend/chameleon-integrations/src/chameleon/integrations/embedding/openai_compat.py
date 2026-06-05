"""OpenAI 兼容协议 embedding 客户端

适配：OpenAI / DeepSeek / Qwen 兼容模式 / vLLM 等。
端点：POST {base_url}/embeddings
"""

from __future__ import annotations

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
# DashScope/Qwen embedding 单批硬上限 25（超出报 400 InvalidParameter）；OpenAI 可更大，
# 但 25 通用安全。大文档按此分批多发几次请求即可。需要更高吞吐的纯 OpenAI 部署可在
# model.json 用 batch_size 覆盖。
_DEFAULT_BATCH_SIZE = 25


class OpenAICompatEmbedding:
    """OpenAI 兼容 embedding 客户端"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dim: int,
        model_code: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        # model = 打给上游的模型名（网关模式下是 upstream_name）；
        # model_code = 逻辑模型 code，trace 归属与计费（calc_cost）按它走。
        self.model = model
        self.model_code = model_code or model
        self.dim = dim
        self.timeout = timeout
        self.batch_size = max(1, batch_size)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        # LangChain Embeddings 基类不 fire 回调 → 用 record_scope 切面落 embedding 节点。
        # 仅在请求级 trace scope 内记（跳过 KB 摄入等无 TraceContext 的批量场景，防刷屏）。
        from chameleon.core.observe.context import (
            ObservationType,
            current_trace_context,
        )

        if current_trace_context() is None:
            results, _, _ = await self._embed_all(texts)
            return results

        from chameleon.integrations.observe.aspect import record_scope

        async with record_scope(
            observation_type=ObservationType.EMBEDDING,
            name=self.model,
            model_code=self.model_code,
            request_payload={
                "model": self.model,
                "dim": self.dim,
                "count": len(texts),
                "total_chars": sum(len(t) for t in texts),
                # 被 embed 的原文预览（每条 ≤200 字、最多 3 条）——查询期通常 1 条，
                # 让溯源能看出"embed 了什么"；全量文本/向量不存（bloat）。
                "texts_preview": [t[:200] for t in texts[:3]],
            },
        ) as scope:
            results, prompt_tokens, total_tokens = await self._embed_all(texts)
            # embedding 只有输入 token（无 completion）；填到 scope，sink 按 model_code
            # 价目自动算 cost_usd（与 generation 同一条计费路径）。
            scope.prompt_tokens = prompt_tokens or None
            scope.total_tokens = total_tokens or None
            scope.response_payload = {
                "count": len(results),
                "dim": self.dim,
                "prompt_tokens": prompt_tokens,
                "total_tokens": total_tokens,
                # 首条向量前 8 维做 sanity check（非全零/NaN），不存全量 1536 维。
                "vector_preview": (
                    [round(float(x), 6) for x in results[0][:8]] if results else None
                ),
            }
            return results

    async def _embed_all(self, texts: list[str]) -> tuple[list[list[float]], int, int]:
        """返回 (向量列表, prompt_tokens 合计, total_tokens 合计)。"""
        results: list[list[float]] = []
        prompt_tokens = 0
        total_tokens = 0
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            vecs, pt, tt = await self._embed_batch(batch)
            results.extend(vecs)
            prompt_tokens += pt
            total_tokens += tt
        return results, prompt_tokens, total_tokens

    async def _embed_batch(
        self, batch: list[str]
    ) -> tuple[list[list[float]], int, int]:
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
        # OpenAI / DashScope 兼容响应带 usage.{prompt_tokens,total_tokens}；缺失则 0。
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or usage.get("total_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or prompt_tokens or 0)
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
        return vectors, prompt_tokens, total_tokens
