"""PR B3 单测：reranker 客户端（BGE/Cohere）+ 注册表 + score 应用"""

from __future__ import annotations

import httpx
import pytest

from chameleon.core.retrieval import Hit, build_reranker
from chameleon.core.retrieval.rerankers import (
    BgeReranker,
    CohereReranker,
    RerankScore,
    apply_rerank_scores,
    make_client_reranker,
)
from chameleon.core.retrieval.rerankers.clients import _parse_rerank_response


def _hits(*ids: int) -> list[Hit]:
    return [Hit(chunk_id=i, content=f"doc-{i}", score=0.5) for i in ids]


# ── 响应解析（双形态容忍） ──────────────────────────────


def test_parse_cohere_style():
    data = {"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.2}]}
    out = _parse_rerank_response(data)
    assert [(s.index, s.score) for s in out] == [(1, 0.9), (0, 0.2)]


def test_parse_tei_style():
    data = [{"index": 0, "score": 0.7}, {"index": 1, "score": 0.1}]
    out = _parse_rerank_response(data)
    assert [(s.index, s.score) for s in out] == [(0, 0.7), (1, 0.1)]


# ── apply_rerank_scores ─────────────────────────────────


def test_apply_scores_resorts_and_writes_meta():
    hits = _hits(10, 11, 12)
    scores = [RerankScore(0, 0.1), RerankScore(1, 0.95), RerankScore(2, 0.5)]
    out = apply_rerank_scores(hits, scores)
    assert [h.chunk_id for h in out] == [11, 12, 10]
    assert out[0].meta["rerank_score"] == 0.95
    assert out[0].score == 0.95


def test_apply_scores_unscored_go_last():
    hits = _hits(10, 11, 12)
    scores = [RerankScore(0, 0.3)]  # 只给第一个打分
    out = apply_rerank_scores(hits, scores)
    assert out[0].chunk_id == 10
    # 未打分的保留原顺序、排后面
    assert {h.chunk_id for h in out[1:]} == {11, 12}


def test_apply_scores_keep_top_k():
    hits = _hits(1, 2, 3, 4)
    scores = [RerankScore(i, float(i)) for i in range(4)]
    out = apply_rerank_scores(hits, scores, keep_top_k=2)
    assert len(out) == 2
    assert [h.chunk_id for h in out] == [4, 3]


# ── client + adapter（mock httpx） ──────────────────────


async def test_bge_client_reranks(monkeypatch):
    captured: dict = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"results": [{"index": 1, "relevance_score": 0.99}, {"index": 0, "relevance_score": 0.1}]}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["payload"] = json
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    client = BgeReranker(base_url="http://localhost:9997/v1")
    reranker = make_client_reranker(client)
    out = await reranker("q", _hits(100, 200))
    assert captured["url"].endswith("/rerank")
    assert captured["payload"]["query"] == "q"
    # index 1 得分更高 → chunk 200 排前
    assert [h.chunk_id for h in out] == [200, 100]
    assert out[0].meta["rerank_score"] == 0.99


async def test_client_reranker_http_failure_falls_back(monkeypatch):
    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    client = BgeReranker(base_url="http://localhost:9997")
    reranker = make_client_reranker(client)
    out = await reranker("q", _hits(1, 2, 3))
    # 失败 → 原顺序
    assert [h.chunk_id for h in out] == [1, 2, 3]


async def test_client_reranker_empty_hits():
    client = BgeReranker(base_url="http://x")
    reranker = make_client_reranker(client)
    assert await reranker("q", []) == []


# ── 注册表 ──────────────────────────────────────────────


def test_build_reranker_default_off():
    assert build_reranker(None) is None
    assert build_reranker({}) is None
    assert build_reranker({"type": "none"}) is None
    assert build_reranker({"type": ""}) is None


def test_build_reranker_bge():
    r = build_reranker({"type": "bge", "base_url": "http://x/v1/rerank"})
    assert callable(r)


def test_build_reranker_bge_missing_base_url_raises():
    with pytest.raises(ValueError, match="base_url"):
        build_reranker({"type": "bge"})


def test_build_reranker_cohere_missing_key_raises():
    with pytest.raises(ValueError, match="api_key"):
        build_reranker({"type": "cohere"})


def test_build_reranker_local_dedupe():
    r = build_reranker({"type": "local_dedupe", "dedupe_threshold": 0.7})
    assert callable(r)


def test_build_reranker_llm_judge_needs_judge_fn():
    with pytest.raises(ValueError, match="judge_fn"):
        build_reranker({"type": "llm_judge"})


def test_build_reranker_unknown_type_raises():
    with pytest.raises(ValueError, match="未知 reranker"):
        build_reranker({"type": "wat"})


async def test_build_reranker_llm_judge_with_fn():
    async def judge(_q, contents):
        return [float(len(c)) for c in contents]

    r = build_reranker({"type": "llm_judge"}, judge_fn=judge)
    assert callable(r)
    out = await r("q", _hits(1, 2))
    assert len(out) == 2


def test_cohere_requires_api_key_on_init():
    with pytest.raises(ValueError):
        CohereReranker(api_key="")
