"""Reranker + 内容去重 —— P22.4 PR #80

提供 3 类 reranker callable，给 HybridPipeline.reranker 用：

1. PassThroughReranker —— 无操作；用于禁用 rerank
2. CosineDedupeReranker —— 用 query embedding 与 hit content embedding 算余弦再排
   + 去掉与已选 hit 内容高度相似（>= dedupe_threshold）的后续 hit
3. LLMJudgeReranker —— 调 judge_fn(query, [contents]) 返排序后的 indices

这些 reranker 都遵循签名：
    async def reranker(query: str, hits: list[Hit]) -> list[Hit]
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Protocol

from chameleon.core.retrieval.hybrid import Hit


class Reranker(Protocol):
    async def __call__(
        self, query: str, hits: list[Hit]
    ) -> list[Hit]:
        ...


# ── 1. PassThrough ─────────────────────────────────────


async def pass_through(query: str, hits: list[Hit]) -> list[Hit]:
    """不做任何重排，原顺序返"""
    _ = query
    return list(hits)


# ── 2. Cosine dedupe（无 LLM，纯字符级 Jaccard 去重） ─────


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = a & b
    union = a | b
    return len(inter) / len(union) if union else 0.0


def make_dedupe_reranker(
    *, dedupe_threshold: float = 0.85
) -> Reranker:
    """按内容 Jaccard 相似度合并近义 chunks

    保留 score 最高的；删除与已选 hit 相似度 >= threshold 的后续 hit。
    """

    async def reranker(query: str, hits: list[Hit]) -> list[Hit]:
        _ = query
        # hits 已按 score 降序；逐个考察
        kept: list[Hit] = []
        token_sets: list[set[str]] = []
        for h in hits:
            ts = _tokens(h.content)
            if any(
                _jaccard(ts, ks) >= dedupe_threshold for ks in token_sets
            ):
                continue
            kept.append(h)
            token_sets.append(ts)
        return kept

    return reranker


# ── 3. LLM judge reranker（接 judge_fn callable） ──────


#: judge_fn 签名：query + list[content] → list[相对得分（0-1）]
JudgeFn = Callable[[str, list[str]], Awaitable[list[float]]]


def make_llm_judge_reranker(
    *,
    judge_fn: JudgeFn,
    keep_top_k: int | None = None,
) -> Reranker:
    """让外部 LLM judge 给每个 hit 打分，按分数重排

    judge_fn 失败时 fallback 到原顺序。
    """

    async def reranker(query: str, hits: list[Hit]) -> list[Hit]:
        if not hits:
            return []
        try:
            scores = await judge_fn(query, [h.content for h in hits])
        except Exception:
            return hits[: keep_top_k or len(hits)]
        if len(scores) != len(hits):
            return hits[: keep_top_k or len(hits)]
        # 给每个 hit 加权 0.5*original + 0.5*judge（保稳）
        for h, s in zip(hits, scores, strict=False):
            h.score = (h.score + float(s)) / 2.0
        ranked = sorted(hits, key=lambda h: h.score, reverse=True)
        return ranked[: keep_top_k] if keep_top_k else ranked

    return reranker


# ── 4. Combined：先 dedupe 再 judge ────────────────────


def make_dedupe_then_judge_reranker(
    *,
    judge_fn: JudgeFn,
    dedupe_threshold: float = 0.85,
    keep_top_k: int | None = None,
) -> Reranker:
    """先 Jaccard 去重，再 LLM judge"""
    dedupe = make_dedupe_reranker(dedupe_threshold=dedupe_threshold)
    judge = make_llm_judge_reranker(
        judge_fn=judge_fn, keep_top_k=keep_top_k
    )

    async def reranker(query: str, hits: list[Hit]) -> list[Hit]:
        deduped = await dedupe(query, hits)
        return await judge(query, deduped)

    return reranker
