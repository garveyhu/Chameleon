"""P22.4 PR #79 单测：hybrid 6 步 pipeline"""

from __future__ import annotations

import pytest

from chameleon.core.retrieval import (
    HybridConfig,
    Hit,
    HybridPipeline,
    dedupe_by_chunk_id,
    fuse_rrf,
    metadata_filter,
)


# ── dedupe ──────────────────────────────────────────────


def test_dedupe_keeps_first_occurrence():
    hits = [
        Hit(chunk_id=1, content="A"),
        Hit(chunk_id=2, content="B"),
        Hit(chunk_id=1, content="A-dup"),
        Hit(chunk_id=3, content="C"),
    ]
    out = dedupe_by_chunk_id(hits)
    assert [h.chunk_id for h in out] == [1, 2, 3]
    assert out[0].content == "A"  # 首次出现的留下


def test_dedupe_empty():
    assert dedupe_by_chunk_id([]) == []


# ── RRF ─────────────────────────────────────────────────


def test_rrf_merges_two_recalls():
    """vec hits = [1,2,3]；kw hits = [3,2,1]；共同高分 chunk 应排前"""
    vec = [Hit(chunk_id=i, content=f"c{i}") for i in [1, 2, 3]]
    kw = [Hit(chunk_id=i, content=f"c{i}") for i in [3, 2, 1]]
    fused = fuse_rrf(vec, kw, k=60)
    assert len(fused) == 3
    # 所有都在；rank 1+3 = chunk 1(vec rank0)+chunk 1(kw rank2)
    #                   chunk 3(vec rank2)+chunk 3(kw rank0)
    # 对称的，chunk 2 应该在中间
    ids = [h.chunk_id for h in fused]
    assert 2 in ids  # 中间位置


def test_rrf_uniqueness_chunk_in_one_recall_only():
    vec = [Hit(chunk_id=1), Hit(chunk_id=2)]
    kw = [Hit(chunk_id=3)]
    fused = fuse_rrf(vec, kw)
    assert {h.chunk_id for h in fused} == {1, 2, 3}


def test_rrf_score_normalized():
    vec = [Hit(chunk_id=1)]
    kw = [Hit(chunk_id=1)]
    fused = fuse_rrf(vec, kw)
    # 单 chunk 在两路都命中 → score=1.0（归一化后）
    assert fused[0].score == pytest.approx(1.0)


def test_rrf_empty_inputs():
    assert fuse_rrf([], []) == []


# ── metadata_filter ────────────────────────────────────


def test_filter_drops_quarantined():
    hits = [
        Hit(chunk_id=1, score=0.9),
        Hit(chunk_id=2, score=0.8, quarantined=True),
    ]
    out = metadata_filter(hits, HybridConfig(drop_quarantined=True))
    assert [h.chunk_id for h in out] == [1]


def test_filter_keeps_quarantined_when_disabled():
    hits = [Hit(chunk_id=1, score=0.9, quarantined=True)]
    out = metadata_filter(hits, HybridConfig(drop_quarantined=False))
    assert [h.chunk_id for h in out] == [1]


def test_filter_allow_collection_ids():
    hits = [
        Hit(chunk_id=1, collection_id=10, score=0.9),
        Hit(chunk_id=2, collection_id=20, score=0.9),
        Hit(chunk_id=3, collection_id=None, score=0.9),  # NULL 不过滤
    ]
    cfg = HybridConfig(allow_collection_ids={10})
    out = metadata_filter(hits, cfg)
    # collection_id=10 留；collection_id=20 剔；collection_id=NULL 留
    assert [h.chunk_id for h in out] == [1, 3]


def test_filter_allow_kinds():
    hits = [
        Hit(chunk_id=1, kind="text", score=0.9),
        Hit(chunk_id=2, kind="image", score=0.9),
    ]
    cfg = HybridConfig(allow_kinds={"text"})
    out = metadata_filter(hits, cfg)
    assert [h.chunk_id for h in out] == [1]


def test_filter_min_score():
    hits = [Hit(chunk_id=1, score=0.9), Hit(chunk_id=2, score=0.3)]
    out = metadata_filter(hits, HybridConfig(min_score=0.5))
    assert [h.chunk_id for h in out] == [1]


# ── 完整 pipeline ─────────────────────────────────────


async def test_pipeline_e2e_with_mock_recalls():
    """vec + kw 召回 → RRF → filter → top_k"""

    async def vec_recall(query: str, n: int) -> list[Hit]:
        return [
            Hit(chunk_id=1, content="A", kind="text"),
            Hit(chunk_id=2, content="B", kind="text"),
            Hit(chunk_id=3, content="C", kind="text"),
        ][:n]

    async def kw_recall(query: str, n: int) -> list[Hit]:
        return [
            Hit(chunk_id=3, content="C", kind="text"),
            Hit(chunk_id=4, content="D", kind="text", quarantined=True),
        ][:n]

    pipeline = HybridPipeline(
        vector_recall=vec_recall,
        keyword_recall=kw_recall,
        config=HybridConfig(top_k=3),
    )
    hits = await pipeline.run("query")
    assert len(hits) == 3
    # chunk 4 quarantined 不在结果
    assert all(h.chunk_id != 4 for h in hits)
    # chunk 3 在两路都命中，应该排在前面（RRF）
    assert hits[0].chunk_id == 3


async def test_pipeline_recall_multiplier_passed_to_callbacks():
    """top_k=5 + recall_multiplier=3 → 召回方收到 n=15"""
    captured_ns: list[int] = []

    async def vec_recall(query: str, n: int) -> list[Hit]:
        captured_ns.append(n)
        return []

    async def kw_recall(query: str, n: int) -> list[Hit]:
        captured_ns.append(n)
        return []

    pipeline = HybridPipeline(
        vector_recall=vec_recall,
        keyword_recall=kw_recall,
        config=HybridConfig(top_k=5, recall_multiplier=3),
    )
    await pipeline.run("q")
    assert captured_ns == [15, 15]


async def test_pipeline_with_reranker_hook():
    """reranker 可重排；返回顺序应被 pipeline 尊重"""

    async def vec_recall(_q, _n):
        return [Hit(chunk_id=1), Hit(chunk_id=2), Hit(chunk_id=3)]

    async def kw_recall(_q, _n):
        return []

    async def rerank(_query: str, hits: list[Hit]) -> list[Hit]:
        # 反转顺序
        return list(reversed(hits))

    pipeline = HybridPipeline(
        vector_recall=vec_recall,
        keyword_recall=kw_recall,
        config=HybridConfig(top_k=3),
        reranker=rerank,
    )
    out = await pipeline.run("q")
    # 没 rerank 时 RRF 顺序 = 1,2,3；rerank 反转 → 3,2,1
    assert [h.chunk_id for h in out] == [3, 2, 1]


async def test_pipeline_empty_recalls():
    async def empty(_q, _n):
        return []

    pipeline = HybridPipeline(
        vector_recall=empty, keyword_recall=empty,
    )
    assert await pipeline.run("q") == []
