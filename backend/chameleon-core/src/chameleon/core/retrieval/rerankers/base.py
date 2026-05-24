"""Reranker 协议 + 公共类型 + score 应用 helper —— PR B3

所有 reranker 都遵循同一 callable 签名（给 HybridPipeline.reranker 用）：
    async def reranker(query: str, hits: list[Hit]) -> list[Hit]

外部模型客户端（BGE / Cohere）返回 [RerankScore]，由 apply_rerank_scores
应用回 hits：写 meta['rerank_score'] 供 hit-test 分项展示（B6），并按 rerank
分数重排。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from chameleon.core.retrieval.hybrid import Hit


class Reranker(Protocol):
    async def __call__(self, query: str, hits: list[Hit]) -> list[Hit]: ...


@dataclass
class RerankScore:
    """单条文档的重排得分（index 对应传入 documents 的下标）"""

    index: int
    score: float


#: LLM judge 签名：query + list[content] → list[相对得分（0-1）]
JudgeFn = Callable[[str, list[str]], Awaitable[list[float]]]


def apply_rerank_scores(
    hits: list[Hit],
    scores: list[RerankScore],
    *,
    keep_top_k: int | None = None,
) -> list[Hit]:
    """把外部模型 [RerankScore] 应用回 hits

    - 命中的 hit：meta['rerank_score'] = score，并把 hit.score 设为 rerank 分
      （rerank 分是最终排序信号；向量 / BM25 分项由 pipeline 单独跟踪供 breakdown）
    - 未被打分的 hit：保留原 score，排在已打分之后
    - 按 rerank 分降序；keep_top_k 截断
    """
    by_index = {s.index: s.score for s in scores}
    scored: list[Hit] = []
    unscored: list[Hit] = []
    for i, h in enumerate(hits):
        if i in by_index:
            rs = float(by_index[i])
            h.meta = {**(h.meta or {}), "rerank_score": rs}
            h.score = rs
            scored.append(h)
        else:
            unscored.append(h)
    scored.sort(key=lambda h: h.score, reverse=True)
    ranked = [*scored, *unscored]
    return ranked[:keep_top_k] if keep_top_k else ranked
