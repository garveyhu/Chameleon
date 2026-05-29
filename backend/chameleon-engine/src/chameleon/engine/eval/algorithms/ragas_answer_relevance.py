"""ragas_answer_relevance —— answer 与 question 的相关性

算法：
  1. 用 judge_fn 让 LLM 反向 "从这个 answer 推出可能的 question"
  2. 取 N 个反向生成的 question，与原 question 算 cosine 相似度（基于词集 Jaccard 兜底，
     若提供 embedder 可走 vector cos sim）
  3. score = 反向生成 question 与原 question 的平均相似度

config:
  { "n_questions": 3 }
"""

from __future__ import annotations

import asyncio

from chameleon.engine.eval.algorithms import register_algorithm
from chameleon.engine.eval.algorithms.judge_helpers import (
    default_judge_fn,
    jaccard_similarity,
)


async def ragas_answer_relevance(
    *,
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: str | None = None,
    config: dict | None = None,
    judge_fn=None,
) -> float:
    _ = contexts, ground_truth
    if not question or not answer:
        return 0.0
    n_q = int((config or {}).get("n_questions", 3))
    n_q = max(1, min(5, n_q))
    judge = judge_fn or default_judge_fn

    prompts = [
        (
            "下面是某次问答的回答。请基于回答，推测一个最可能的原始问题。"
            "只输出问题文本，不要解释。\n\n"
            f"回答：{answer}"
        )
    ] * n_q
    inferred = await asyncio.gather(*[judge(p) for p in prompts])

    sims = [jaccard_similarity(question, q) for q in inferred if q]
    if not sims:
        return 0.0
    return sum(sims) / len(sims)


register_algorithm("ragas_answer_relevance", ragas_answer_relevance)
