"""chameleon.core.retrieval —— 检索算子库

P22.4 PR #79：抽出 hybrid 6 步管道为独立模块，便于：
- 单测每一步（无 DB 依赖）
- 接 reranker hook（PR #80）
- 接多模态 image vector（PR #82）

Pipeline（6 步）：
    1) vector 召回 top_k * 2
    2) BM25 召回 top_k * 2
    3) dedupe（按 chunk_id；可选内容相似度合并）
    4) RRF 融合排序
    5) metadata filter（quarantined / collection / kind / tags）
    6) optional reranker hook → 取 top_k

红线（plan §2 P22）：
- ⛔ quarantined chunks 不应出现在结果（半软删保留）
"""

from chameleon.core.retrieval.expander import (
    CompleteFn,
    expand_queries,
    hyde_query,
)
from chameleon.core.retrieval.hybrid import (
    Hit,
    HybridConfig,
    HybridPipeline,
    QueryExpander,
    dedupe_by_chunk_id,
    fuse_rrf,
    fuse_rrf_many,
    metadata_filter,
)
from chameleon.core.retrieval.rerankers import (
    BgeReranker,
    CohereReranker,
    JudgeFn,
    Reranker,
    RerankScore,
    apply_rerank_scores,
    build_reranker,
    make_client_reranker,
    make_dedupe_reranker,
    make_dedupe_then_judge_reranker,
    make_llm_judge_reranker,
    pass_through,
)
from chameleon.core.retrieval.vlm_caption import (
    CaptionFn,
    CaptionResult,
    VLMClient,
    generate_caption,
    generate_captions_batch,
)

__all__ = [
    "BgeReranker",
    "CaptionFn",
    "CaptionResult",
    "CohereReranker",
    "CompleteFn",
    "HybridConfig",
    "Hit",
    "HybridPipeline",
    "JudgeFn",
    "QueryExpander",
    "Reranker",
    "RerankScore",
    "VLMClient",
    "apply_rerank_scores",
    "build_reranker",
    "dedupe_by_chunk_id",
    "expand_queries",
    "fuse_rrf",
    "fuse_rrf_many",
    "generate_caption",
    "generate_captions_batch",
    "hyde_query",
    "make_client_reranker",
    "make_dedupe_reranker",
    "make_dedupe_then_judge_reranker",
    "make_llm_judge_reranker",
    "metadata_filter",
    "pass_through",
]
