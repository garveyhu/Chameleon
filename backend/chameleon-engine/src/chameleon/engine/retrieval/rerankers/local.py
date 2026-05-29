"""本地 reranker（无外部模型）—— P22.4 PR #80（B3 迁入 rerankers 包）

3 类纯本地 reranker，给 HybridPipeline.reranker 用：

1. pass_through                —— 无操作；用于禁用 rerank
2. make_dedupe_reranker        —— 字符级 Jaccard 去重近义 chunk
3. make_llm_judge_reranker     —— 调 judge_fn(query, [contents]) 重排
4. make_dedupe_then_judge_reranker —— 先去重再 judge

这些 reranker 都遵循签名：
    async def reranker(query: str, hits: list[Hit]) -> list[Hit]
"""

from __future__ import annotations

import re

from chameleon.engine.retrieval.hybrid import Hit
from chameleon.engine.retrieval.rerankers.base import JudgeFn, Reranker

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


def make_dedupe_reranker(*, dedupe_threshold: float = 0.85) -> Reranker:
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
            if any(_jaccard(ts, ks) >= dedupe_threshold for ks in token_sets):
                continue
            kept.append(h)
            token_sets.append(ts)
        return kept

    return reranker


# ── 3. LLM judge reranker（接 judge_fn callable） ──────


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
        return ranked[:keep_top_k] if keep_top_k else ranked

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
    judge = make_llm_judge_reranker(judge_fn=judge_fn, keep_top_k=keep_top_k)

    async def reranker(query: str, hits: list[Hit]) -> list[Hit]:
        deduped = await dedupe(query, hits)
        return await judge(query, deduped)

    return reranker
