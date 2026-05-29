"""rerankers —— reranker 客户端 + 本地算子 + 注册表（PR B3）

- 本地（无外部模型）：pass_through / dedupe / llm_judge —— local.py
- 外部模型客户端：BgeReranker / CohereReranker —— clients.py
- 注册表：build_reranker(config) → Reranker | None（默认关）—— registry.py

统一签名：async reranker(query, hits) -> list[Hit]
"""

from chameleon.engine.retrieval.rerankers.base import (
    JudgeFn,
    Reranker,
    RerankScore,
    apply_rerank_scores,
)
from chameleon.engine.retrieval.rerankers.clients import (
    BgeReranker,
    CohereReranker,
    make_client_reranker,
)
from chameleon.engine.retrieval.rerankers.local import (
    make_dedupe_reranker,
    make_dedupe_then_judge_reranker,
    make_llm_judge_reranker,
    pass_through,
)
from chameleon.engine.retrieval.rerankers.registry import build_reranker

__all__ = [
    "BgeReranker",
    "CohereReranker",
    "JudgeFn",
    "Reranker",
    "RerankScore",
    "apply_rerank_scores",
    "build_reranker",
    "make_client_reranker",
    "make_dedupe_reranker",
    "make_dedupe_then_judge_reranker",
    "make_llm_judge_reranker",
    "pass_through",
]
