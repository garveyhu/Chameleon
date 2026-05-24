"""PR B5 单测：retrieval pipeline 编排（DB-free，注入 mock recall）"""

from __future__ import annotations

from chameleon.core.retrieval.hybrid import Hit
from chameleon.core.retrieval.pipeline import RetrievalParams, _assemble_and_run


def _hit(cid: int, *, kind: str = "text", content: str = "") -> Hit:
    return Hit(chunk_id=cid, content=content or f"c{cid}", kind=kind, score=0.5)


async def _run(params, *, vec, kw, complete_fn=None):
    vec_capture: dict[int, float] = {}
    kw_capture: dict[int, float] = {}

    async def vec_recall(_q, _n):
        out = []
        for cid, score in vec:
            vec_capture[cid] = score
            out.append(_hit(cid, kind="image" if cid >= 100 else "text"))
        return out

    async def kw_recall(_q, _n):
        out = []
        for cid, score in kw:
            kw_capture[cid] = score
            out.append(_hit(cid))
        return out

    return await _assemble_and_run(
        params=params,
        query="q",
        vec_recall=vec_recall,
        kw_recall=kw_recall,
        vec_capture=vec_capture,
        kw_capture=kw_capture,
        complete_fn=complete_fn,
    )


# ── allow_kinds ─────────────────────────────────────────


def test_allow_kinds_text_only_by_default():
    assert RetrievalParams(kb_id=1, embedding_model="m").allow_kinds() == {"text"}


def test_allow_kinds_includes_image_when_enabled():
    p = RetrievalParams(kb_id=1, embedding_model="m", include_images=True)
    assert p.allow_kinds() == {"text", "image"}


# ── breakdown 回填 ──────────────────────────────────────


async def test_breakdown_backfilled_on_hits():
    params = RetrievalParams(kb_id=1, embedding_model="m", top_k=5)
    out = await _run(
        params, vec=[(1, 0.9), (2, 0.7)], kw=[(1, 0.4), (3, 0.8)]
    )
    by_id = {h.chunk_id: h for h in out}
    # chunk 1 两路命中 → 同时有 vector_score + bm25_score
    assert by_id[1].meta["vector_score"] == 0.9
    assert by_id[1].meta["bm25_score"] == 0.4
    # chunk 2 仅向量
    assert by_id[2].meta["vector_score"] == 0.7
    assert "bm25_score" not in by_id[2].meta
    # chunk 3 仅关键词
    assert by_id[3].meta["bm25_score"] == 0.8
    assert "vector_score" not in by_id[3].meta


# ── image kind 过滤 ─────────────────────────────────────


async def test_image_chunk_dropped_when_images_disabled():
    params = RetrievalParams(kb_id=1, embedding_model="m", top_k=5)
    out = await _run(params, vec=[(1, 0.9), (100, 0.95)], kw=[])
    # include_images=False → kind=image (cid 100) 被 metadata_filter 剔除
    assert {h.chunk_id for h in out} == {1}


async def test_image_chunk_kept_when_images_enabled():
    params = RetrievalParams(
        kb_id=1, embedding_model="m", top_k=5, include_images=True
    )
    out = await _run(params, vec=[(1, 0.9), (100, 0.95)], kw=[])
    assert {h.chunk_id for h in out} == {1, 100}


# ── reranker 配置驱动 ───────────────────────────────────


async def test_reranker_off_by_default():
    params = RetrievalParams(kb_id=1, embedding_model="m", top_k=5)
    out = await _run(params, vec=[(1, 0.9), (2, 0.8)], kw=[])
    assert len(out) == 2


async def test_invalid_reranker_config_does_not_crash():
    # bge 缺 base_url → build_reranker 抛 ValueError → pipeline 吞掉，rerank 关
    params = RetrievalParams(
        kb_id=1, embedding_model="m", top_k=5, reranker_config={"type": "bge"}
    )
    out = await _run(params, vec=[(1, 0.9)], kw=[])
    assert [h.chunk_id for h in out] == [1]


# ── multi-query / HyDE 用注入的 complete_fn ────────────


async def test_multi_query_uses_injected_complete_fn():
    calls: list[str] = []

    async def complete(prompt: str) -> str:
        calls.append(prompt)
        return "变体一\n变体二"

    params = RetrievalParams(
        kb_id=1, embedding_model="m", top_k=5, multi_query_count=3
    )
    out = await _run(params, vec=[(1, 0.9)], kw=[], complete_fn=complete)
    # expander 调了注入的 complete_fn（未触发 default_complete_fn → 不需 LLM 配置）
    assert calls
    assert [h.chunk_id for h in out] == [1]


async def test_hyde_uses_injected_complete_fn():
    calls: list[str] = []

    async def complete(prompt: str) -> str:
        calls.append(prompt)
        return "假设答案"

    params = RetrievalParams(
        kb_id=1, embedding_model="m", top_k=5, use_hyde=True
    )
    out = await _run(params, vec=[(1, 0.9)], kw=[], complete_fn=complete)
    assert calls  # HyDE 调了 complete_fn
    assert [h.chunk_id for h in out] == [1]


async def test_hyde_reranks_with_original_query_not_hypothetical():
    """HyDE + reranker：reranker 应拿原始 query 打分，而非假设答案"""
    seen: list[str] = []

    async def complete(_prompt: str) -> str:
        return "这是一段假设性答案"

    async def vec_recall(_q, _n):
        return [_hit(1), _hit(2)]

    async def kw_recall(_q, _n):
        return []

    vec_capture: dict[int, float] = {}
    kw_capture: dict[int, float] = {}

    async def reranker_spy(query, hits):
        seen.append(query)
        return hits

    # 用 local_dedupe 之外的方式注入 reranker：直接走 _assemble_and_run 的 reranker_config
    # 这里改用 monkeypatch 风格不便，故用 hybrid 直测覆盖（见 test_retrieval_expander）。
    # 本测确认 _assemble_and_run 把原 query 透传给 pipeline.run 的 rerank_query。
    from chameleon.core.retrieval import pipeline as pl

    params = RetrievalParams(
        kb_id=1, embedding_model="m", top_k=5, use_hyde=True
    )

    # 临时桩：让 build_reranker 返回 spy
    orig = pl.build_reranker
    pl.build_reranker = lambda cfg: reranker_spy  # type: ignore[assignment]
    params.reranker_config = {"type": "local_dedupe"}
    try:
        await pl._assemble_and_run(
            params=params,
            query="原始用户问题",
            vec_recall=vec_recall,
            kw_recall=kw_recall,
            vec_capture=vec_capture,
            kw_capture=kw_capture,
            complete_fn=complete,
        )
    finally:
        pl.build_reranker = orig
    assert seen == ["原始用户问题"]
