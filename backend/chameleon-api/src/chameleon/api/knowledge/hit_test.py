"""KB hit-test —— 检索调试 + score breakdown（v1.1 B6）

单一检索路径：走 core.retrieval.pipeline.retrieve，返回每条命中的分项得分：
  - vector_score  向量召回原始余弦相似度
  - bm25_score    BM25(ts_rank) 归一化分
  - rerank_score  reranker 重排分（启用 reranker 时才有）
缺省项为 None。UI 渲染留 Agent D（D5 三栏 hit-test 分项条形图）。

admin /v1/admin/kbs/{kb_id}/search 与 retrieval evaluation 共用本服务，
统一检索语义（hybrid RRF / 过滤 quarantined / multi-query / HyDE / reranker）。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.data.models import Document, KnowledgeBase
from chameleon.engine.retrieval.pipeline import RetrievalParams, retrieve

_MODES = ("vector", "keyword", "hybrid")


@dataclass
class HitTestResult:
    chunk_id: int
    doc_id: int
    seq: int
    content: str
    score: float
    document_title: str
    kind: str = "text"
    source_url: str | None = None
    vector_score: float | None = None
    bm25_score: float | None = None
    rerank_score: float | None = None

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "seq": self.seq,
            "content": self.content,
            "score": self.score,
            "document_title": self.document_title,
            "kind": self.kind,
            "source_url": self.source_url,
            "vector_score": self.vector_score,
            "bm25_score": self.bm25_score,
            "rerank_score": self.rerank_score,
        }


async def run_hit_test(
    session: AsyncSession,
    *,
    kb_id: int,
    query: str,
    top_k: int = 5,
    min_score: float = 0.0,
    mode: str | None = None,
    doc_ids: list[int] | None = None,
    tags: list[str] | None = None,
    metadata_filters: dict[str, str] | None = None,
    include_images: bool | None = None,
    multi_query_count: int = 0,
    use_hyde: bool = False,
    reranker_config: dict | None = None,
) -> list[HitTestResult]:
    """跑一次 hit-test，返回带 score breakdown 的命中列表"""
    if not query or not query.strip():
        raise ValidationError(message="query 不能为空")

    kb = await _get_kb(session, kb_id)
    resolved_mode = mode or kb.recall_mode or "vector"
    if resolved_mode not in _MODES:
        raise ValidationError(message=f"unsupported recall_mode: {resolved_mode}")

    candidate_doc_ids = await _resolve_doc_filter(
        session,
        kb_id=kb.id,
        doc_ids=doc_ids,
        tags=tags,
        metadata_filters=metadata_filters,
    )
    if (doc_ids or tags or metadata_filters) and not candidate_doc_ids:
        return []

    kb_meta = kb.meta or {}
    params = RetrievalParams(
        kb_id=kb.id,
        embedding_model=kb.embedding_model,
        top_k=top_k,
        recall_mode=resolved_mode,
        include_images=(
            include_images
            if include_images is not None
            else bool(kb_meta.get("include_images"))
        ),
        doc_ids=candidate_doc_ids,
        multi_query_count=multi_query_count,
        use_hyde=use_hyde,
        reranker_config=reranker_config or kb_meta.get("reranker"),
        min_score=min_score,
    )
    hits = await retrieve(session, params, query)
    return [
        HitTestResult(
            chunk_id=h.chunk_id,
            doc_id=h.doc_id or 0,
            seq=h.seq or 0,
            content=h.content,
            score=round(h.score, 6),
            document_title=h.document_title or "",
            kind=h.kind,
            source_url=(h.meta or {}).get("source_url"),
            vector_score=(h.meta or {}).get("vector_score"),
            bm25_score=(h.meta or {}).get("bm25_score"),
            rerank_score=(h.meta or {}).get("rerank_score"),
        )
        for h in hits
    ]


# ── helpers ─────────────────────────────────────────────


async def _get_kb(session: AsyncSession, kb_id: int) -> KnowledgeBase:
    kb = (
        await session.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == kb_id, KnowledgeBase.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if kb is None:
        raise BusinessError(
            ResultCode.KnowledgeBaseNotFound, message=f"kb 不存在: {kb_id}"
        )
    return kb


async def _resolve_doc_filter(
    session: AsyncSession,
    *,
    kb_id: int,
    doc_ids: list[int] | None,
    tags: list[str] | None,
    metadata_filters: dict[str, str] | None = None,
) -> set[int] | None:
    """返候选 doc_id 集；None 表示无过滤。tags / metadata 均收敛为 doc_id 集求交。"""
    if not tags and not doc_ids and not metadata_filters:
        return None
    candidate: set[int] | None = None
    if tags:
        stmt = select(Document.id).where(
            Document.kb_id == kb_id, Document.deleted_at.is_(None)
        )
        for t in tags:
            stmt = stmt.where(cast(Document.tags, JSONB).contains([t]))
        candidate = set((await session.execute(stmt)).scalars().all())
    if metadata_filters:
        # 按 Document.meta 的 key=value 过滤（meta->>key == value，文本比较，AND）
        meta = cast(Document.meta, JSONB)
        stmt = select(Document.id).where(
            Document.kb_id == kb_id, Document.deleted_at.is_(None)
        )
        for k, v in metadata_filters.items():
            stmt = stmt.where(meta[k].astext == v)
        rows = set((await session.execute(stmt)).scalars().all())
        candidate = rows if candidate is None else candidate & rows
    if doc_ids:
        candidate = set(doc_ids) if candidate is None else candidate & set(doc_ids)
    return candidate
