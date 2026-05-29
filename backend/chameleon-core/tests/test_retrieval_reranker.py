"""P22.4 PR #80 单测：Reranker + 内容去重"""

from __future__ import annotations

from chameleon.core.retrieval import (
    Hit,
    make_dedupe_reranker,
    make_dedupe_then_judge_reranker,
    make_llm_judge_reranker,
    pass_through,
)

# ── pass_through ───────────────────────────────────────


async def test_pass_through_preserves_order():
    hits = [Hit(chunk_id=i) for i in [3, 1, 2]]
    out = await pass_through("q", hits)
    assert [h.chunk_id for h in out] == [3, 1, 2]


# ── dedupe reranker ────────────────────────────────────


async def test_dedupe_removes_near_duplicates():
    """两个 content 高度相似的 hit → 保留第一个"""
    rerank = make_dedupe_reranker(dedupe_threshold=0.5)
    hits = [
        Hit(chunk_id=1, score=0.9, content="apple banana cherry orange"),
        Hit(chunk_id=2, score=0.8, content="apple banana cherry pear"),  # 与 1 jaccard=0.6
        Hit(chunk_id=3, score=0.7, content="totally different content here"),
    ]
    out = await rerank("q", hits)
    ids = [h.chunk_id for h in out]
    assert 1 in ids
    assert 3 in ids
    assert 2 not in ids  # 与 1 高度相似被去重


async def test_dedupe_keeps_higher_score():
    rerank = make_dedupe_reranker(dedupe_threshold=0.5)
    # 第一个 score 高 → 留；第二个内容相似但 score 低 → 去掉
    hits = [
        Hit(chunk_id=1, score=0.95, content="alpha beta gamma"),
        Hit(chunk_id=2, score=0.50, content="alpha beta delta"),
    ]
    out = await rerank("q", hits)
    assert [h.chunk_id for h in out] == [1]


async def test_dedupe_low_threshold_keeps_all_different():
    """阈值 0.95 → 不同内容都保留"""
    rerank = make_dedupe_reranker(dedupe_threshold=0.95)
    hits = [
        Hit(chunk_id=1, content="cat dog bird"),
        Hit(chunk_id=2, content="cat dog fish"),
        Hit(chunk_id=3, content="apple"),
    ]
    out = await rerank("q", hits)
    assert {h.chunk_id for h in out} == {1, 2, 3}


async def test_dedupe_empty():
    rerank = make_dedupe_reranker()
    out = await rerank("q", [])
    assert out == []


# ── LLM judge reranker ────────────────────────────────


async def test_llm_judge_reranks_by_score():
    """judge 给 [0.1, 0.9, 0.5] → 重排为 [b, c, a]"""

    async def judge_fn(query, contents):
        # 倒序：第 2 个最高分
        return [0.1, 0.9, 0.5]

    rerank = make_llm_judge_reranker(judge_fn=judge_fn)
    hits = [
        Hit(chunk_id=1, score=0.5, content="a"),
        Hit(chunk_id=2, score=0.5, content="b"),
        Hit(chunk_id=3, score=0.5, content="c"),
    ]
    out = await rerank("q", hits)
    # (0.5+0.1)/2=0.3 vs (0.5+0.9)/2=0.7 vs (0.5+0.5)/2=0.5 → 排序 2,3,1
    assert [h.chunk_id for h in out] == [2, 3, 1]


async def test_llm_judge_fallback_on_judge_exception():
    """judge 抛错 → fallback 原顺序"""

    async def judge_fn(query, contents):
        raise RuntimeError("judge unavailable")

    rerank = make_llm_judge_reranker(judge_fn=judge_fn)
    hits = [Hit(chunk_id=1), Hit(chunk_id=2)]
    out = await rerank("q", hits)
    assert [h.chunk_id for h in out] == [1, 2]


async def test_llm_judge_fallback_on_length_mismatch():
    """judge 返回 score 长度不匹配 hits → 返原顺序"""

    async def judge_fn(query, contents):
        return [0.5]  # 长度 1 ≠ hits 长度 2

    rerank = make_llm_judge_reranker(judge_fn=judge_fn)
    hits = [Hit(chunk_id=1), Hit(chunk_id=2)]
    out = await rerank("q", hits)
    assert [h.chunk_id for h in out] == [1, 2]


async def test_llm_judge_keep_top_k():
    async def judge_fn(query, contents):
        return [0.9, 0.5, 0.1]

    rerank = make_llm_judge_reranker(judge_fn=judge_fn, keep_top_k=2)
    hits = [Hit(chunk_id=i, content=f"c{i}") for i in [1, 2, 3]]
    out = await rerank("q", hits)
    assert len(out) == 2


async def test_llm_judge_empty():
    async def judge_fn(query, contents):
        return []

    rerank = make_llm_judge_reranker(judge_fn=judge_fn)
    out = await rerank("q", [])
    assert out == []


# ── combined dedupe + judge ──────────────────────────


async def test_combined_dedupe_then_judge():
    """先 dedupe 去掉相似 hit；剩余的让 judge 重排"""

    async def judge_fn(query, contents):
        # judge 偏好 chunk 3（'totally different'）排第一
        return [0.4, 0.95]

    rerank = make_dedupe_then_judge_reranker(
        judge_fn=judge_fn, dedupe_threshold=0.5, keep_top_k=2
    )
    hits = [
        Hit(chunk_id=1, score=0.9, content="apple banana cherry"),
        Hit(chunk_id=2, score=0.8, content="apple banana fruit"),  # 与 1 相似 → 去
        Hit(chunk_id=3, score=0.7, content="totally different content"),
    ]
    out = await rerank("q", hits)
    # dedupe 留下 1+3；judge 偏好 3 → 排序 3 在前
    ids = [h.chunk_id for h in out]
    assert ids == [3, 1]
