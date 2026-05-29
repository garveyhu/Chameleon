"""DB-aware 检索编排器 —— v1.1 PR B5

把纯算子（hybrid / expander / rerankers）接到真实 pgvector + PG FTS 上：

    query
      → [可选] multi-query / HyDE 扩展（LLM）
      → 向量召回（pgvector cosine） + BM25 召回（PG ts_rank）
      → RRF 融合 + metadata filter（kind / collection / quarantined）
      → [可选] reranker（registry 配置驱动，默认关）
      → top_k

多模态（B5）：图片 chunk 以「caption → 文本向量」落进同一 1536 空间（见
embedding/image.py），故无需独立召回路；include_images=True 时仅在 allow_kinds
放行 kind='image'，同一次向量召回即可命中图片 chunk。

score breakdown（供 B6 hit-test）：召回阶段把每路原始分（vector / bm25）记进
score map，最终对每条命中回填 meta['vector_score'] / meta['bm25_score']；
reranker 命中再写 meta['rerank_score']。

红线：
- ⛔ 坚持单 PG + pgvector；不引入 ES / Milvus / Qdrant
- ⛔ reranker 可选，默认关（走 reranker_config）
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from loguru import logger
from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.embedding import get_embedding_client
from chameleon.data.models import Chunk, Document
from chameleon.data.utils import tokenizer
from chameleon.engine.retrieval.expander import (
    CompleteFn,
    expand_queries,
    hyde_query,
)
from chameleon.engine.retrieval.hybrid import Hit, HybridConfig, HybridPipeline
from chameleon.engine.retrieval.rerankers import build_reranker


@dataclass
class RetrievalParams:
    """一次检索的全部配置（KB / collection 配置映射到这里）"""

    kb_id: int
    embedding_model: str
    top_k: int = 5
    #: vector / keyword / hybrid
    recall_mode: str = "hybrid"
    #: 放行图片 chunk（多模态 KB）
    include_images: bool = False
    #: 文档级过滤（admin hit-test 用）
    doc_ids: set[int] | None = None
    collection_ids: set[int] | None = None
    #: multi-query 变体数（含原 query）；<=1 关闭
    multi_query_count: int = 0
    #: HyDE：用假设答案替代原 query 做 embed
    use_hyde: bool = False
    #: reranker 配置（registry.build_reranker）；None / {"type":"none"} = 关
    reranker_config: dict | None = None
    min_score: float = 0.0
    recall_multiplier: int = 2

    def allow_kinds(self) -> set[str]:
        return {"text", "image"} if self.include_images else {"text"}


#: 召回结果 + 原始分 map（capture 供 breakdown 回填）
_ScoreMap = dict[int, float]


def _row_to_hit(row, *, raw_score: float) -> Hit:
    meta = dict(row.meta or {})
    if row.source_url:
        meta["source_url"] = row.source_url
    # parent-child：命中的是精准 child，但返回所属 parent 大块作上下文
    content = row.content
    if getattr(row, "parent_content", None):
        meta["child_content"] = row.content
        meta["is_parent_context"] = True
        content = row.parent_content
    return Hit(
        chunk_id=row.id,
        doc_id=row.doc_id,
        seq=row.seq,
        content=content,
        score=raw_score,
        document_title=row.title,
        quarantined=bool(row.quarantined),
        collection_id=row.collection_id,
        kind=row.kind or "text",
        meta=meta,
    )


def _build_vector_recall(
    session: AsyncSession,
    params: RetrievalParams,
    *,
    capture: _ScoreMap,
) -> Callable[[str, int], Awaitable[list[Hit]]]:
    async def recall(query: str, n: int) -> list[Hit]:
        client = get_embedding_client(params.embedding_model)
        vecs = await client.embed([query])
        if not vecs:
            return []
        distance = Chunk.embedding.cosine_distance(vecs[0]).label("distance")
        stmt = (
            select(
                Chunk.id,
                Chunk.doc_id,
                Chunk.seq,
                Chunk.content,
                Chunk.parent_content,
                Chunk.kind,
                Chunk.collection_id,
                Chunk.quarantined,
                Chunk.source_url,
                Chunk.meta,
                Document.title,
                distance,
            )
            .join(Document, Chunk.doc_id == Document.id)
            .where(
                Chunk.kb_id == params.kb_id,
                Document.deleted_at.is_(None),
                Document.enabled.is_(True),
                Chunk.enabled.is_(True),
            )
            .order_by(distance.asc())
            .limit(n)
        )
        if params.doc_ids is not None:
            stmt = stmt.where(Chunk.doc_id.in_(params.doc_ids))
        if params.collection_ids is not None:
            stmt = stmt.where(Chunk.collection_id.in_(params.collection_ids))
        rows = (await session.execute(stmt)).all()
        hits: list[Hit] = []
        for r in rows:
            score = 1.0 - float(r.distance)
            capture[r.id] = max(capture.get(r.id, score), score)
            hits.append(_row_to_hit(r, raw_score=score))
        return hits

    return recall


def _build_keyword_recall(
    session: AsyncSession,
    params: RetrievalParams,
    *,
    capture: _ScoreMap,
) -> Callable[[str, int], Awaitable[list[Hit]]]:
    async def recall(query: str, n: int) -> list[Hit]:
        # jieba 切词 → OR 连接（中文按词召回；content_tsv 也是切词版）。
        # 无有效词项（纯标点 / 空）直接空召回，避免 to_tsquery 语法错误。
        terms = tokenizer.keyword_query_terms(query)
        if not terms:
            return []
        ts_query = func.to_tsquery("simple", " | ".join(terms))
        tsv_col = literal_column("content_tsv")
        rank = func.ts_rank(tsv_col, ts_query).label("rank")
        stmt = (
            select(
                Chunk.id,
                Chunk.doc_id,
                Chunk.seq,
                Chunk.content,
                Chunk.parent_content,
                Chunk.kind,
                Chunk.collection_id,
                Chunk.quarantined,
                Chunk.source_url,
                Chunk.meta,
                Document.title,
                rank,
            )
            .join(Document, Chunk.doc_id == Document.id)
            .where(
                Chunk.kb_id == params.kb_id,
                Document.deleted_at.is_(None),
                Document.enabled.is_(True),
                Chunk.enabled.is_(True),
                tsv_col.op("@@")(ts_query),
            )
            .order_by(rank.desc())
            .limit(n)
        )
        if params.doc_ids is not None:
            stmt = stmt.where(Chunk.doc_id.in_(params.doc_ids))
        if params.collection_ids is not None:
            stmt = stmt.where(Chunk.collection_id.in_(params.collection_ids))
        rows = (await session.execute(stmt)).all()
        if not rows:
            return []
        max_rank = max(float(r.rank) for r in rows) or 1.0
        hits: list[Hit] = []
        for r in rows:
            score = float(r.rank) / max_rank
            capture[r.id] = max(capture.get(r.id, score), score)
            hits.append(_row_to_hit(r, raw_score=score))
        return hits

    return recall


async def _empty_recall(_q: str, _n: int) -> list[Hit]:
    return []


def default_complete_fn() -> CompleteFn:
    """生产用 LLM 文本补全适配器（multi-query / HyDE）"""
    from langchain_core.messages import HumanMessage

    from chameleon.integrations.llms.factory import resolve_llm

    async def complete(prompt: str) -> str:
        # #30：per-request 经 channel 路由解析 LLM（无 session → 自开短 session）
        client = await resolve_llm()
        resp = await client.ainvoke([HumanMessage(content=prompt)])
        content = resp.content
        return content if isinstance(content, str) else str(content)

    return complete


RecallFn = Callable[[str, int], Awaitable[list[Hit]]]


async def _assemble_and_run(
    *,
    params: RetrievalParams,
    query: str,
    vec_recall: RecallFn,
    kw_recall: RecallFn,
    vec_capture: _ScoreMap,
    kw_capture: _ScoreMap,
    complete_fn: CompleteFn | None,
) -> list[Hit]:
    """组合 HyDE / multi-query / reranker 跑 HybridPipeline + 回填 breakdown

    DB-free 核心：recall 与 capture 由调用方注入，便于单测。
    """
    # HyDE：用假设答案替代检索 query（仅影响向量召回的 embed 输入）
    effective_query = query
    if params.use_hyde:
        effective_query = await hyde_query(
            query, complete_fn=complete_fn or default_complete_fn()
        )

    # multi-query expander（注入 LLM）
    expander = None
    if params.multi_query_count > 1:
        fn = complete_fn or default_complete_fn()

        async def expander(q: str) -> list[str]:
            return await expand_queries(
                q, complete_fn=fn, n=params.multi_query_count
            )

    reranker = None
    if params.reranker_config:
        try:
            reranker = build_reranker(params.reranker_config)
        except ValueError:
            logger.exception("invalid reranker_config | rerank disabled")

    config = HybridConfig(
        top_k=params.top_k,
        recall_multiplier=params.recall_multiplier,
        allow_kinds=params.allow_kinds(),
        allow_collection_ids=params.collection_ids,
        min_score=params.min_score,
        multi_query_count=params.multi_query_count,
    )
    pipeline = HybridPipeline(
        vector_recall=vec_recall,
        keyword_recall=kw_recall,
        config=config,
        reranker=reranker,
        query_expander=expander,
    )
    # HyDE 下 effective_query 是假设答案（召回用）；reranker 用原始 query 打分
    hits = await pipeline.run(effective_query, rerank_query=query)

    # 回填 score breakdown（B6）
    for h in hits:
        meta = dict(h.meta or {})
        if h.chunk_id in vec_capture:
            meta["vector_score"] = round(vec_capture[h.chunk_id], 6)
        if h.chunk_id in kw_capture:
            meta["bm25_score"] = round(kw_capture[h.chunk_id], 6)
        h.meta = meta

    # parent-child：同一 parent 的多个 child 命中 → 内容已是 parent 上下文，去重保最高分
    deduped: list[Hit] = []
    seen_parents: set[str] = set()
    for h in hits:
        if h.meta.get("is_parent_context"):
            if h.content in seen_parents:
                continue
            seen_parents.add(h.content)
        deduped.append(h)
    return deduped


async def retrieve(
    session: AsyncSession,
    params: RetrievalParams,
    query: str,
    *,
    complete_fn: CompleteFn | None = None,
) -> list[Hit]:
    """跑完整检索管道，返最终命中（meta 含 vector/bm25/rerank 分项）

    complete_fn：multi-query / HyDE 用的 LLM 补全；None 时按需取默认适配器。
    """
    if not query or not query.strip():
        return []
    mode = params.recall_mode or "hybrid"

    vec_capture: _ScoreMap = {}
    kw_capture: _ScoreMap = {}
    vec_recall = (
        _build_vector_recall(session, params, capture=vec_capture)
        if mode in ("vector", "hybrid")
        else _empty_recall
    )
    kw_recall = (
        _build_keyword_recall(session, params, capture=kw_capture)
        if mode in ("keyword", "hybrid")
        else _empty_recall
    )
    return await _assemble_and_run(
        params=params,
        query=query,
        vec_recall=vec_recall,
        kw_recall=kw_recall,
        vec_capture=vec_capture,
        kw_capture=kw_capture,
        complete_fn=complete_fn,
    )
