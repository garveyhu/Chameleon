"""PR B6 单测：hit-test score breakdown 映射"""

from __future__ import annotations

import pytest

from chameleon.api.knowledge import hit_test
from chameleon.core.api.exceptions import ValidationError
from chameleon.core.retrieval.hybrid import Hit


class _FakeKB:
    id = 1
    embedding_model = "stub-embed"
    recall_mode = "hybrid"
    meta: dict = {}


@pytest.fixture
def _patch(monkeypatch):
    captured: dict = {}

    async def fake_get_kb(_session, _kb_id):
        return _FakeKB()

    async def fake_retrieve(_session, params, query, **_kw):
        captured["params"] = params
        captured["query"] = query
        return [
            Hit(
                chunk_id=10,
                doc_id=2,
                seq=3,
                content="hit content",
                score=0.88,
                document_title="Doc",
                kind="text",
                meta={
                    "vector_score": 0.91,
                    "bm25_score": 0.42,
                    "rerank_score": 0.97,
                },
            ),
            Hit(
                chunk_id=11,
                doc_id=2,
                seq=4,
                content="image cap",
                score=0.5,
                kind="image",
                meta={"vector_score": 0.5, "source_url": "http://x/i.png"},
            ),
        ]

    monkeypatch.setattr(hit_test, "_get_kb", fake_get_kb)
    monkeypatch.setattr(hit_test, "retrieve", fake_retrieve)
    return captured


async def test_breakdown_fields_mapped(_patch):
    out = await hit_test.run_hit_test(None, kb_id=1, query="q", top_k=5)
    assert out[0].vector_score == 0.91
    assert out[0].bm25_score == 0.42
    assert out[0].rerank_score == 0.97
    assert out[0].kind == "text"
    # 第二条仅 vector_score；bm25 / rerank 为 None；带 source_url
    assert out[1].vector_score == 0.5
    assert out[1].bm25_score is None
    assert out[1].rerank_score is None
    assert out[1].kind == "image"
    assert out[1].source_url == "http://x/i.png"


async def test_to_dict_shape(_patch):
    out = await hit_test.run_hit_test(None, kb_id=1, query="q")
    d = out[0].to_dict()
    assert set(d) == {
        "chunk_id", "doc_id", "seq", "content", "score", "document_title",
        "kind", "source_url", "vector_score", "bm25_score", "rerank_score",
    }


async def test_options_passed_to_params(_patch):
    await hit_test.run_hit_test(
        None,
        kb_id=1,
        query="q",
        top_k=8,
        mode="vector",
        multi_query_count=3,
        use_hyde=True,
        include_images=True,
    )
    params = _patch["params"]
    assert params.top_k == 8
    assert params.recall_mode == "vector"
    assert params.multi_query_count == 3
    assert params.use_hyde is True
    assert params.include_images is True


async def test_empty_query_raises(_patch):
    with pytest.raises(ValidationError):
        await hit_test.run_hit_test(None, kb_id=1, query="   ")


async def test_invalid_mode_raises(_patch):
    with pytest.raises(ValidationError, match="recall_mode"):
        await hit_test.run_hit_test(None, kb_id=1, query="q", mode="bogus")
