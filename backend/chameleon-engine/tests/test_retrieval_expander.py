"""PR B1/B2 单测：query 扩展（multi-query + HyDE）+ multi-query pipeline"""

from __future__ import annotations

from chameleon.engine.retrieval import (
    Hit,
    HybridConfig,
    HybridPipeline,
    expand_queries,
    fuse_rrf_many,
    hyde_query,
)

# ── expand_queries ──────────────────────────────────────


async def test_expand_queries_parses_lines_and_keeps_original():
    async def complete(_prompt: str) -> str:
        return "1. 变体一\n2) 变体二\n- 变体三"

    out = await expand_queries("原问题", complete_fn=complete, n=3)
    # 原 query 排首位 + 3 个去序号/符号的变体
    assert out[0] == "原问题"
    assert out[1:] == ["变体一", "变体二", "变体三"]


async def test_expand_queries_dedupes_and_caps_to_n():
    async def complete(_prompt: str) -> str:
        return "alpha\nalpha\nbeta\ngamma\ndelta"

    out = await expand_queries("q", complete_fn=complete, n=2)
    # n=2 截断（在去序号后取前 2 个变体）+ 原 query
    assert out[0] == "q"
    assert len(out) == 3  # q + 2 变体
    assert out[1] == "alpha"
    assert out[2] == "beta"


async def test_expand_queries_llm_failure_falls_back_to_original():
    async def boom(_prompt: str) -> str:
        raise RuntimeError("llm down")

    out = await expand_queries("仅此一条", complete_fn=boom, n=3)
    assert out == ["仅此一条"]


async def test_expand_queries_n_zero_returns_original_only():
    async def complete(_prompt: str) -> str:
        return "should-not-be-used"

    out = await expand_queries("q", complete_fn=complete, n=0)
    assert out == ["q"]


async def test_expand_queries_without_original():
    async def complete(_prompt: str) -> str:
        return "v1\nv2"

    out = await expand_queries(
        "q", complete_fn=complete, n=2, include_original=False
    )
    assert out == ["v1", "v2"]


# ── hyde_query ──────────────────────────────────────────


async def test_hyde_returns_hypothetical_answer():
    async def complete(_prompt: str) -> str:
        return "  这是一段假设性答案。  "

    out = await hyde_query("问题", complete_fn=complete)
    assert out == "这是一段假设性答案。"


async def test_hyde_failure_falls_back_to_query():
    async def boom(_prompt: str) -> str:
        raise RuntimeError("timeout")

    assert await hyde_query("原问题", complete_fn=boom) == "原问题"


async def test_hyde_empty_falls_back_to_query():
    async def empty(_prompt: str) -> str:
        return "   "

    assert await hyde_query("原问题", complete_fn=empty) == "原问题"


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
