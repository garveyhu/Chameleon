"""Hybrid 6 步检索管道 —— P22.4 PR #79

纯算子模块：召回 callable 由调用方注入；本模块只负责融合、去重、过滤、rerank。
不依赖 DB / pgvector / LLM 客户端，便于单测。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Hit:
    """单条检索结果"""

    chunk_id: int
    doc_id: int | None = None
    seq: int | None = None
    content: str = ""
    score: float = 0.0
    document_title: str | None = None
    #: P21.3 quarantined chunks 进 filter 时被剔
    quarantined: bool = False
    #: P20.3 / P22.4 KB collection 关联
    collection_id: int | None = None
    #: P22.4 chunk kind（text / image / ...）—— PR #82
    kind: str = "text"
    #: 任意业务自定义 metadata（tags 等）
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "seq": self.seq,
            "content": self.content,
            "score": self.score,
            "document_title": self.document_title,
            "kind": self.kind,
            **({"collection_id": self.collection_id}
               if self.collection_id is not None else {}),
            **({"meta": self.meta} if self.meta else {}),
        }


@dataclass
class HybridConfig:
    """hybrid pipeline 入参 / 阈值"""

    top_k: int = 5
    #: 召回阶段每路抓多少（默认 top_k * 2）
    recall_multiplier: int = 2
    #: RRF 中的 k 常数
    rrf_k: int = 60
    #: filter 阶段保留的 collection_ids（None = 不过滤）
    allow_collection_ids: set[int] | None = None
    #: filter 阶段保留的 kinds（默认仅 text，PR #82 起可加 image）
    allow_kinds: set[str] = field(default_factory=lambda: {"text"})
    #: 是否过滤 quarantined（强烈推荐 True）
    drop_quarantined: bool = True
    #: 最小 score 阈值（最后一层 cutoff）
    min_score: float = 0.0


# ── 单步算子 ────────────────────────────────────────────


def dedupe_by_chunk_id(hits: Iterable[Hit]) -> list[Hit]:
    """同 chunk_id 仅保留首次出现"""
    seen: set[int] = set()
    out: list[Hit] = []
    for h in hits:
        if h.chunk_id in seen:
            continue
        seen.add(h.chunk_id)
        out.append(h)
    return out


def fuse_rrf(
    vec_hits: list[Hit],
    kw_hits: list[Hit],
    *,
    k: int = 60,
) -> list[Hit]:
    """Reciprocal Rank Fusion：score = sum(1/(k + rank+1))

    返按 RRF score 降序排列的合并列表（去重 by chunk_id）。
    """
    score_by_id: dict[int, float] = {}
    obj_by_id: dict[int, Hit] = {}

    for rank, h in enumerate(vec_hits):
        cid = h.chunk_id
        score_by_id[cid] = score_by_id.get(cid, 0.0) + 1.0 / (k + rank + 1)
        obj_by_id.setdefault(cid, h)

    for rank, h in enumerate(kw_hits):
        cid = h.chunk_id
        score_by_id[cid] = score_by_id.get(cid, 0.0) + 1.0 / (k + rank + 1)
        obj_by_id.setdefault(cid, h)

    if not score_by_id:
        return []

    sorted_ids = sorted(
        score_by_id, key=lambda c: score_by_id[c], reverse=True
    )
    max_score = score_by_id[sorted_ids[0]] or 1.0
    return [
        Hit(
            chunk_id=cid,
            doc_id=obj_by_id[cid].doc_id,
            seq=obj_by_id[cid].seq,
            content=obj_by_id[cid].content,
            score=score_by_id[cid] / max_score,
            document_title=obj_by_id[cid].document_title,
            quarantined=obj_by_id[cid].quarantined,
            collection_id=obj_by_id[cid].collection_id,
            kind=obj_by_id[cid].kind,
            meta=obj_by_id[cid].meta,
        )
        for cid in sorted_ids
    ]


def metadata_filter(hits: list[Hit], config: HybridConfig) -> list[Hit]:
    """按 quarantined / collection_id / kind / min_score 过滤"""
    out: list[Hit] = []
    for h in hits:
        if config.drop_quarantined and h.quarantined:
            continue
        if (
            config.allow_collection_ids is not None
            and h.collection_id is not None
            and h.collection_id not in config.allow_collection_ids
        ):
            continue
        if config.allow_kinds and h.kind not in config.allow_kinds:
            continue
        if h.score < config.min_score:
            continue
        out.append(h)
    return out


# ── 完整 pipeline ────────────────────────────────────────


#: 召回 callable 签名：query + top_k → list[Hit]
RecallFn = Callable[[str, int], Awaitable[list[Hit]]]


class HybridPipeline:
    """6 步 hybrid 检索

    用法：
        pipeline = HybridPipeline(
            vector_recall=my_vector_search,
            keyword_recall=my_bm25_search,
            config=HybridConfig(top_k=5),
        )
        hits = await pipeline.run("query")

    可选注入 reranker_fn（PR #80）：
        pipeline = HybridPipeline(..., reranker=my_rerank_fn)
    """

    def __init__(
        self,
        *,
        vector_recall: RecallFn,
        keyword_recall: RecallFn,
        config: HybridConfig | None = None,
        reranker: Callable[[str, list[Hit]], Awaitable[list[Hit]]] | None = None,
    ) -> None:
        self.vector_recall = vector_recall
        self.keyword_recall = keyword_recall
        self.config = config or HybridConfig()
        self.reranker = reranker

    async def run(self, query: str) -> list[Hit]:
        c = self.config
        recall_n = c.top_k * c.recall_multiplier

        # 1) vector 召回
        vec_hits = await self.vector_recall(query, recall_n)
        # 2) BM25 召回
        kw_hits = await self.keyword_recall(query, recall_n)
        # 3) dedupe（各路内部）
        vec_hits = dedupe_by_chunk_id(vec_hits)
        kw_hits = dedupe_by_chunk_id(kw_hits)
        # 4) RRF 融合
        fused = fuse_rrf(vec_hits, kw_hits, k=c.rrf_k)
        # 5) metadata filter
        filtered = metadata_filter(fused, c)
        # 6) optional reranker + top_k cut
        if self.reranker is not None and filtered:
            filtered = await self.reranker(query, filtered)
        return filtered[: c.top_k]
