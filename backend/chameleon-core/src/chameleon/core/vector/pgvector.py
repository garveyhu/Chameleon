"""pgvector 实现（v1 默认）

策略：
- chunks 表已带 HNSW(cosine) 索引（migration 0002）
- 用 SQLAlchemy ORM + pgvector.sqlalchemy.Vector
- cosine distance 用 `<=>` 操作符（pgvector）
- score = 1 - distance（cosine 距离 0~2 → 相似度 1~-1）
- 自管 session（不依赖 FastAPI Depends；可被 in-process API / worker 调用）
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import Chunk
from chameleon.core.utils import tokenizer
from chameleon.core.vector.base import ChunkHit, ChunkPayload, VectorStore


class PgVectorStore(VectorStore):
    backend = "pgvector"

    async def upsert(
        self,
        *,
        kb_id: int,
        doc_id: int,
        chunks: list[ChunkPayload],
    ) -> None:
        if not chunks:
            return
        async with AsyncSessionLocal() as session:
            try:
                # 先删 doc_id 下的同 seq（简单 upsert：旧的删了重插，等价语义）
                seqs = [c.seq for c in chunks]
                await session.execute(
                    delete(Chunk).where(
                        Chunk.doc_id == doc_id,
                        Chunk.seq.in_(seqs),
                    )
                )
                session.add_all(
                    Chunk(
                        kb_id=kb_id,
                        doc_id=doc_id,
                        seq=c.seq,
                        content=c.content,
                        # 中文关键词召回：落库即存 jieba 切词版（含 qa_question 一并切，
                        # 让问句关键词也进 BM25 索引）
                        content_search=tokenizer.segment_for_index(
                            f"{c.content} {c.qa_question or ''}"
                        ),
                        embedding=c.embedding,
                        token_count=c.token_count,
                        meta=c.meta,
                        parent_content=c.parent_content,
                        qa_question=c.qa_question,
                    )
                    for c in chunks
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def search(
        self,
        *,
        kb_id: int,
        query_vec: list[float],
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[ChunkHit]:
        async with AsyncSessionLocal() as session:
            return await self._search_in_session(
                session,
                kb_id=kb_id,
                query_vec=query_vec,
                top_k=top_k,
                min_score=min_score,
            )

    async def _search_in_session(
        self,
        session: AsyncSession,
        *,
        kb_id: int,
        query_vec: list[float],
        top_k: int,
        min_score: float,
    ) -> list[ChunkHit]:
        # cosine distance 操作符
        distance = Chunk.embedding.cosine_distance(query_vec).label("distance")
        stmt = (
            select(
                Chunk.id,
                Chunk.doc_id,
                Chunk.seq,
                Chunk.content,
                Chunk.meta,
                distance,
            )
            .where(Chunk.kb_id == kb_id, Chunk.enabled.is_(True))
            .order_by(distance.asc())
            .limit(top_k)
        )
        rows = (await session.execute(stmt)).all()

        hits: list[ChunkHit] = []
        for row in rows:
            score = 1.0 - float(row.distance)
            if score < min_score:
                continue
            hits.append(
                ChunkHit(
                    id=row.id,
                    doc_id=row.doc_id,
                    seq=row.seq,
                    content=row.content,
                    score=score,
                    meta=row.meta,
                )
            )
        return hits

    async def delete(self, *, kb_id: int, doc_id: int | None = None) -> int:
        async with AsyncSessionLocal() as session:
            try:
                stmt = delete(Chunk).where(Chunk.kb_id == kb_id)
                if doc_id is not None:
                    stmt = stmt.where(Chunk.doc_id == doc_id)
                result = await session.execute(stmt)
                await session.commit()
                return int(result.rowcount or 0)
            except Exception:
                await session.rollback()
                raise

    async def healthcheck(self) -> bool:
        async with AsyncSessionLocal() as session:
            try:
                await session.execute(select(func.count(Chunk.id)).limit(1))
                return True
            except Exception:
                return False
