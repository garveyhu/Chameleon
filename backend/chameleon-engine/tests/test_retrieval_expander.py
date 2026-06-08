"""multi-query 融合 + pipeline 单测。

query 扩展算子（expand_queries / hyde_query）已迁至 aikit（见
chameleon-aikit/tests/test_retrieval_expander.py）；本文件保留 engine 侧的 RRF 融合
与 multi-query pipeline 行为测试（用本地 stub expander，不依赖 aikit）。
"""

from __future__ import annotations

from chameleon.engine.retrieval import (
    Hit,
    HybridConfig,
    HybridPipeline,
    fuse_rrf_many,
)

# ── fuse_rrf_many ───────────────────────────────────────


def test_fuse_rrf_many_merges_three_lists():
    lists = [
        [Hit(chunk_id=1), Hit(chunk_id=2)],
        [Hit(chunk_id=2), Hit(chunk_id=3)],
        [Hit(chunk_id=2)],
    ]
    out = fuse_rrf_many(lists)
    # chunk 2 出现在三路全部 → 最高分排第一
    assert out[0].chunk_id == 2
    assert {h.chunk_id for h in out} == {1, 2, 3}


def test_fuse_rrf_many_empty():
    assert fuse_rrf_many([]) == []
    assert fuse_rrf_many([[], []]) == []


# ── multi-query pipeline ────────────────────────────────


async def test_pipeline_multi_query_expands_and_fuses():
    """multi_query_count=2 + expander → 每个变体都被召回，调用次数翻倍"""
    seen_queries: list[str] = []

    async def vec_recall(q: str, _n: int) -> list[Hit]:
        seen_queries.append(q)
        # 不同变体命中不同 chunk，验证融合覆盖面
        return {
            "原q": [Hit(chunk_id=1, content="A")],
            "变体q": [Hit(chunk_id=2, content="B")],
        }.get(q, [])

    async def kw_recall(_q: str, _n: int) -> list[Hit]:
        return []

    async def expander(_q: str) -> list[str]:
        return ["原q", "变体q"]

    pipeline = HybridPipeline(
        vector_recall=vec_recall,
        keyword_recall=kw_recall,
        config=HybridConfig(top_k=5, multi_query_count=2),
        query_expander=expander,
    )
    out = await pipeline.run("原q")
    # 两个变体都跑了向量召回
    assert set(seen_queries) == {"原q", "变体q"}
    # 两路命中合并 → chunk 1 + 2 都在
    assert {h.chunk_id for h in out} == {1, 2}


async def test_pipeline_multi_query_off_when_count_le_1():
    """multi_query_count<=1 → 即便注入 expander 也不扩展"""
    seen: list[str] = []

    async def vec_recall(q: str, _n: int) -> list[Hit]:
        seen.append(q)
        return [Hit(chunk_id=1)]

    async def kw_recall(_q: str, _n: int) -> list[Hit]:
        return []

    async def expander(_q: str) -> list[str]:
        raise AssertionError("expander should not be called")

    pipeline = HybridPipeline(
        vector_recall=vec_recall,
        keyword_recall=kw_recall,
        config=HybridConfig(top_k=5, multi_query_count=1),
        query_expander=expander,
    )
    out = await pipeline.run("q")
    assert seen == ["q"]
    assert [h.chunk_id for h in out] == [1]


async def test_pipeline_rerank_query_overrides_run_query():
    """rerank_query 注入 → reranker 拿到的是 rerank_query 而非召回 query"""
    seen_rerank_query: list[str] = []

    async def vec_recall(_q, _n):
        return [Hit(chunk_id=1), Hit(chunk_id=2)]

    async def kw_recall(_q, _n):
        return []

    async def rerank(query: str, hits: list[Hit]) -> list[Hit]:
        seen_rerank_query.append(query)
        return hits

    pipeline = HybridPipeline(
        vector_recall=vec_recall,
        keyword_recall=kw_recall,
        config=HybridConfig(top_k=3),
        reranker=rerank,
    )
    await pipeline.run("假设答案做召回", rerank_query="原始用户问题")
    assert seen_rerank_query == ["原始用户问题"]


async def test_pipeline_multi_query_expander_failure_degrades():
    """expander 抛错 → 退化为单原 query，不崩"""

    async def vec_recall(_q: str, _n: int) -> list[Hit]:
        return [Hit(chunk_id=7)]

    async def kw_recall(_q: str, _n: int) -> list[Hit]:
        return []

    async def expander(_q: str) -> list[str]:
        raise RuntimeError("expander boom")

    pipeline = HybridPipeline(
        vector_recall=vec_recall,
        keyword_recall=kw_recall,
        config=HybridConfig(top_k=5, multi_query_count=3),
        query_expander=expander,
    )
    out = await pipeline.run("q")
    assert [h.chunk_id for h in out] == [7]
