"""PgVectorStore 集成测试 —— 真实 PG + pgvector"""

import secrets

import pytest
from sqlalchemy import delete

from chameleon.core.db import AsyncSessionLocal
from chameleon.core.models import Chunk, Document, KnowledgeBase
from chameleon.core.vector.base import ChunkPayload
from chameleon.core.vector.pgvector import PgVectorStore


def _vec(values: list[float], dim: int = 1536) -> list[float]:
    """构造 dim 维向量；values 是前几位，剩余补 0"""
    return values + [0.0] * (dim - len(values))


@pytest.fixture
async def kb_doc():
    rand = secrets.token_hex(3)
    async with AsyncSessionLocal() as s:
        kb = KnowledgeBase(
            kb_key=f"test-vec-{rand}",
            name="vec-test",
            embedding_model="text-embedding-3-small",
            embedding_dim=1536,
        )
        s.add(kb)
        await s.flush()
        doc = Document(
            kb_id=kb.id,
            title="doc1",
            source_type="text",
            status="ready",
        )
        s.add(doc)
        await s.commit()
        await s.refresh(kb)
        await s.refresh(doc)
        kb_id, doc_id = kb.id, doc.id

    yield kb_id, doc_id

    async with AsyncSessionLocal() as s:
        await s.execute(delete(Chunk).where(Chunk.kb_id == kb_id))
        await s.execute(delete(Document).where(Document.id == doc_id))
        await s.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
        await s.commit()


async def test_upsert_and_search(kb_doc) -> None:
    kb_id, doc_id = kb_doc
    store = PgVectorStore()

    await store.upsert(
        kb_id=kb_id,
        doc_id=doc_id,
        chunks=[
            ChunkPayload(content="alpha", embedding=_vec([1.0, 0.0]), seq=1),
            ChunkPayload(content="beta", embedding=_vec([0.0, 1.0]), seq=2),
            ChunkPayload(content="gamma", embedding=_vec([0.9, 0.1]), seq=3),
        ],
    )

    # query 向量接近 [1,0]，应返 alpha + gamma（按相似度）
    hits = await store.search(
        kb_id=kb_id,
        query_vec=_vec([1.0, 0.0]),
        top_k=3,
    )
    assert len(hits) == 3
    assert hits[0].content == "alpha"
    assert hits[0].score > hits[1].score
    # alpha 是完全匹配 → score ~ 1
    assert hits[0].score > 0.99


async def test_search_min_score_filter(kb_doc) -> None:
    kb_id, doc_id = kb_doc
    store = PgVectorStore()
    await store.upsert(
        kb_id=kb_id,
        doc_id=doc_id,
        chunks=[
            ChunkPayload(content="hi", embedding=_vec([1.0, 0.0]), seq=1),
            ChunkPayload(content="far", embedding=_vec([-1.0, 0.0]), seq=2),
        ],
    )
    hits = await store.search(
        kb_id=kb_id,
        query_vec=_vec([1.0, 0.0]),
        top_k=10,
        min_score=0.5,
    )
    contents = [h.content for h in hits]
    assert "hi" in contents
    # 反向向量 cosine distance ~ 2 → score ~ -1 < 0.5
    assert "far" not in contents


async def test_delete_by_doc(kb_doc) -> None:
    kb_id, doc_id = kb_doc
    store = PgVectorStore()
    await store.upsert(
        kb_id=kb_id,
        doc_id=doc_id,
        chunks=[
            ChunkPayload(content="x", embedding=_vec([1.0]), seq=1),
            ChunkPayload(content="y", embedding=_vec([0.5]), seq=2),
        ],
    )
    deleted = await store.delete(kb_id=kb_id, doc_id=doc_id)
    assert deleted == 2
    hits = await store.search(kb_id=kb_id, query_vec=_vec([1.0]), top_k=5)
    assert hits == []


async def test_kb_isolation(kb_doc) -> None:
    """另一个 KB 的 chunks 不应被搜到"""
    kb_id, doc_id = kb_doc
    store = PgVectorStore()
    await store.upsert(
        kb_id=kb_id,
        doc_id=doc_id,
        chunks=[ChunkPayload(content="kb1-x", embedding=_vec([1.0]), seq=1)],
    )

    # 用另一个不存在的 kb_id 搜
    hits = await store.search(kb_id=999_999_999, query_vec=_vec([1.0]), top_k=5)
    assert hits == []


async def test_upsert_seq_replaces(kb_doc) -> None:
    """相同 doc_id+seq 二次写入 → 替换"""
    kb_id, doc_id = kb_doc
    store = PgVectorStore()
    await store.upsert(
        kb_id=kb_id,
        doc_id=doc_id,
        chunks=[ChunkPayload(content="v1", embedding=_vec([1.0]), seq=1)],
    )
    await store.upsert(
        kb_id=kb_id,
        doc_id=doc_id,
        chunks=[ChunkPayload(content="v2", embedding=_vec([1.0]), seq=1)],
    )
    hits = await store.search(kb_id=kb_id, query_vec=_vec([1.0]), top_k=5)
    assert len(hits) == 1
    assert hits[0].content == "v2"
