"""admin 视角的 KB 文档管理服务

业务方走 chameleon-api 的 /v1/knowledge/*；本模块给 admin 用，
直接以 kb_id 操作，覆盖完整 Dify 级 CRUD + ingest 编排。
"""

from __future__ import annotations

import asyncio
import mimetypes
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.knowledge import storage
from chameleon.api.knowledge.ingest import run_ingest_task
from chameleon.core.api.exceptions import (
    BusinessError,
    DocumentNotFoundError,
    ResultCode,
    ValidationError,
)
from chameleon.core.api.response import PageParams, PageResult
from chameleon.core.embedding import get_embedding_client
from chameleon.core.models import Chunk, Document, KnowledgeBase, Task
from chameleon.core.utils.snowflake import next_id
from chameleon.core.vector import get_store

# ── 公共：KB 取 / 校验 ─────────────────────────────────────


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


# ── KB 列表 / 详情 / 修改（admin） ────────────────────────


async def _kb_counts(session: AsyncSession, kb_id: int) -> tuple[int, int]:
    """返 (document_count, chunk_count)"""
    doc_count = (
        await session.execute(
            select(func.count(Document.id)).where(
                Document.kb_id == kb_id, Document.deleted_at.is_(None)
            )
        )
    ).scalar_one()
    chunk_count = (
        await session.execute(
            select(func.count(Chunk.id))
            .join(Document, Chunk.doc_id == Document.id)
            .where(Document.kb_id == kb_id, Document.deleted_at.is_(None))
        )
    ).scalar_one()
    return doc_count, chunk_count


async def list_kbs_with_stats(
    session: AsyncSession, page: PageParams
) -> tuple[PageResult[KnowledgeBase], list[tuple[int, int]]]:
    """返 (paged kbs, 与 items 等长的 (doc_count, chunk_count) 列表)"""
    base = select(KnowledgeBase).where(KnowledgeBase.deleted_at.is_(None))
    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                base.order_by(KnowledgeBase.created_at.desc())
                .offset(page.offset)
                .limit(page.limit)
            )
        )
        .scalars()
        .all()
    )
    counts = [await _kb_counts(session, kb.id) for kb in rows]
    return (
        PageResult(
            items=list(rows), total=total, page=page.page, page_size=page.page_size
        ),
        counts,
    )


async def get_kb_with_stats(
    session: AsyncSession, kb_id: int
) -> tuple[KnowledgeBase, int, int]:
    kb = await _get_kb(session, kb_id)
    doc_count, chunk_count = await _kb_counts(session, kb.id)
    return kb, doc_count, chunk_count


async def update_kb(
    session: AsyncSession,
    *,
    kb_id: int,
    name: str | None = None,
    description: str | None = None,
    chunk_strategy: dict | None = None,
    default_top_k: int | None = None,
    recall_mode: str | None = None,
) -> KnowledgeBase:
    kb = (
        await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
    ).scalar_one_or_none()
    if kb is None:
        raise BusinessError(
            ResultCode.KnowledgeBaseNotFound, message=f"kb 不存在: {kb_id}"
        )
    if name is not None:
        kb.name = name
    if description is not None:
        kb.description = description
    if chunk_strategy is not None:
        kb.chunk_strategy = chunk_strategy
    if default_top_k is not None:
        kb.default_top_k = default_top_k
    if recall_mode is not None:
        kb.recall_mode = recall_mode
    await session.flush()
    await session.refresh(kb)
    return kb


async def list_kb_chunks(
    session: AsyncSession, *, kb_id: int, page: PageParams
) -> PageResult[Chunk]:
    base = (
        select(Chunk)
        .join(Document, Chunk.doc_id == Document.id)
        .where(Document.kb_id == kb_id, Document.deleted_at.is_(None))
    )
    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                base.order_by(Chunk.doc_id, Chunk.seq)
                .offset(page.offset)
                .limit(page.limit)
            )
        )
        .scalars()
        .all()
    )
    return PageResult(
        items=list(rows), total=total, page=page.page, page_size=page.page_size
    )


# ── 创建：upload / url / text ────────────────────────────


async def create_text_document(
    session: AsyncSession,
    *,
    kb_id: int,
    name: str,
    content: str,
) -> tuple[int, int]:
    """创建 text 类型 doc + 任务，返 (document_id, task_id)。"""
    kb = await _get_kb(session, kb_id)
    if not content or not content.strip():
        raise ValidationError(message="content 不能为空")

    doc = Document(
        kb_id=kb.id,
        title=name,
        source_type="text",
        source_uri=None,
        mime_type="text/plain",
        status="pending",
        size_bytes=len(content.encode("utf-8")),
        meta={"content": content},
    )
    session.add(doc)
    await session.flush()
    task_id = await _enqueue_ingest(session, kb_id=kb.id, doc_id=doc.id)
    return doc.id, task_id


async def create_url_document(
    session: AsyncSession,
    *,
    kb_id: int,
    url: str,
    name: str | None = None,
) -> tuple[int, int]:
    kb = await _get_kb(session, kb_id)
    if not url:
        raise ValidationError(message="url 不能为空")

    doc = Document(
        kb_id=kb.id,
        title=name or url,
        source_type="url",
        source_uri=url,
        mime_type=None,  # 由 ingest worker 抓 content-type 决定
        status="pending",
    )
    session.add(doc)
    await session.flush()
    task_id = await _enqueue_ingest(session, kb_id=kb.id, doc_id=doc.id)
    return doc.id, task_id


async def create_upload_document(
    session: AsyncSession,
    *,
    kb_id: int,
    filename: str,
    content: bytes,
    content_type: str | None = None,
) -> tuple[int, int]:
    """落 doc 行 + 把字节写到 MinIO + 排 ingest 任务。"""
    kb = await _get_kb(session, kb_id)
    if not content:
        raise ValidationError(message=f"上传文件为空: {filename}")
    mime = content_type or mimetypes.guess_type(filename)[0]
    doc_id = next_id()  # 提前生成，保证 object key 可预先计算
    object_key = storage.object_key(kb.id, doc_id)
    storage.write_upload(kb.id, doc_id, content, content_type=mime)

    doc = Document(
        id=doc_id,
        kb_id=kb.id,
        title=filename,
        source_type="upload",
        source_uri=object_key,
        mime_type=mime,
        status="pending",
        size_bytes=len(content),
    )
    session.add(doc)
    await session.flush()
    task_id = await _enqueue_ingest(session, kb_id=kb.id, doc_id=doc.id)
    return doc.id, task_id


async def create_upload_documents_bulk(
    session: AsyncSession,
    *,
    kb_id: int,
    bundles: list[tuple[str, bytes, str | None]],
) -> list[dict]:
    """批量上传；返 [{document_id, task_id}, ...]，调用方负责 commit + spawn。"""
    out: list[dict] = []
    for filename, content, content_type in bundles:
        doc_id, task_id = await create_upload_document(
            session,
            kb_id=kb_id,
            filename=filename,
            content=content,
            content_type=content_type,
        )
        out.append({"document_id": doc_id, "task_id": task_id})
    return out


# ── 列表 / 详情 / 删除 / 状态 ────────────────────────────


async def list_documents(
    session: AsyncSession,
    *,
    kb_id: int,
    page: PageParams,
    status: str | None = None,
    tag: str | None = None,
) -> tuple[KnowledgeBase, PageResult[Document]]:
    kb = await _get_kb(session, kb_id)
    stmt = select(Document).where(
        Document.kb_id == kb.id, Document.deleted_at.is_(None)
    )
    if status:
        stmt = stmt.where(Document.status == status)
    if tag:
        # tags @> '["tag"]'，要求 jsonb cast
        stmt = stmt.where(cast(Document.tags, JSONB).contains([tag]))
    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                stmt.order_by(Document.created_at.desc())
                .offset(page.offset)
                .limit(page.limit)
            )
        )
        .scalars()
        .all()
    )
    return kb, PageResult(
        items=list(rows), total=total, page=page.page, page_size=page.page_size
    )


async def get_document(
    session: AsyncSession, *, kb_id: int, doc_id: int
) -> Document:
    kb = await _get_kb(session, kb_id)
    row = (
        await session.execute(
            select(Document).where(
                Document.id == doc_id,
                Document.kb_id == kb.id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise DocumentNotFoundError(message=f"文档不存在: {doc_id}")
    return row


async def update_document(
    session: AsyncSession,
    *,
    kb_id: int,
    doc_id: int,
    tags: list[str] | None = None,
    meta: dict | None = None,
    chunk_strategy: dict | None = None,
) -> Document:
    """更新 document tag / metadata / chunk_strategy；不重新分块。"""
    row = await get_document(session, kb_id=kb_id, doc_id=doc_id)
    if tags is not None:
        row.tags = list(tags)
    if meta is not None:
        row.meta = {**(row.meta or {}), **meta}
    if chunk_strategy is not None:
        row.chunk_strategy = chunk_strategy
    await session.flush()
    return row


async def reindex_document(
    session: AsyncSession, *, kb_id: int, doc_id: int
) -> tuple[int, int]:
    """重新分块单个文档：清旧 chunks → 标 pending → 排 ingest 任务。
    返 (document_id, task_id)。
    """
    doc = await get_document(session, kb_id=kb_id, doc_id=doc_id)
    if doc.status == "processing":
        raise ValidationError(message="文档正在处理中，无法 reindex")
    # 删旧 chunks（向量库）；ingest worker 也会自删，这里早做一次让 UI 立刻清零
    store = get_store()
    await store.delete(kb_id=kb_id, doc_id=doc_id)
    doc.status = "pending"
    doc.status_message = None
    doc.chunk_count = 0
    doc.token_count = 0
    await session.flush()
    task_id = await _enqueue_ingest(session, kb_id=kb_id, doc_id=doc.id)
    return doc.id, task_id


async def reindex_all_documents(
    session: AsyncSession, *, kb_id: int
) -> list[dict]:
    """批量重分块当前 KB 全部 done/failed 文档。"""
    kb = await _get_kb(session, kb_id)
    rows = (
        (
            await session.execute(
                select(Document).where(
                    Document.kb_id == kb.id,
                    Document.deleted_at.is_(None),
                    Document.status.in_(("ready", "failed")),
                )
            )
        )
        .scalars()
        .all()
    )
    out: list[dict] = []
    for doc in rows:
        store = get_store()
        await store.delete(kb_id=kb.id, doc_id=doc.id)
        doc.status = "pending"
        doc.status_message = None
        doc.chunk_count = 0
        doc.token_count = 0
        await session.flush()
        task_id = await _enqueue_ingest(session, kb_id=kb.id, doc_id=doc.id)
        out.append({"document_id": doc.id, "task_id": task_id})
    return out


async def delete_document(
    session: AsyncSession, *, kb_id: int, doc_id: int
) -> Document:
    """软删 doc + 物理删 chunks + 删 MinIO 对象。"""
    row = await get_document(session, kb_id=kb_id, doc_id=doc_id)

    # 删向量库
    store = get_store()
    await store.delete(kb_id=kb_id, doc_id=doc_id)

    # 删对象存储
    if row.source_type == "upload" and row.source_uri:
        try:
            storage.delete_upload(row.source_uri)
        except Exception:  # noqa: BLE001
            logger.exception("delete object failed: {}", row.source_uri)

    row.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    return row


async def list_document_chunks(
    session: AsyncSession,
    *,
    kb_id: int,
    doc_id: int,
    page: PageParams,
) -> tuple[Document, PageResult[Chunk]]:
    """分页查询某 doc 的 chunks（按 seq 升序）"""
    doc = await get_document(session, kb_id=kb_id, doc_id=doc_id)
    stmt = select(Chunk).where(Chunk.doc_id == doc.id)
    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                stmt.order_by(Chunk.seq).offset(page.offset).limit(page.limit)
            )
        )
        .scalars()
        .all()
    )
    return doc, PageResult(
        items=list(rows), total=total, page=page.page, page_size=page.page_size
    )


# ── search（admin playground） ────────────────────────────


async def search_chunks(
    session: AsyncSession,
    *,
    kb_id: int,
    query: str,
    top_k: int = 5,
    min_score: float = 0.0,
    doc_ids: list[int] | None = None,
    tags: list[str] | None = None,
    mode: str | None = None,
) -> list[dict]:
    """三模式 chunk 检索；可按 doc_ids / tags 过滤。
    mode: vector / keyword / hybrid（None 时走 kb.recall_mode）
    返 [{chunk_id, doc_id, seq, content, score, document_title}]
    """
    kb = await _get_kb(session, kb_id)
    if not query.strip():
        raise ValidationError(message="query 不能为空")
    mode = mode or kb.recall_mode or "vector"
    if mode not in ("vector", "keyword", "hybrid"):
        raise ValidationError(message=f"unsupported recall_mode: {mode}")

    candidate_doc_ids = await _resolve_doc_filter(
        session, kb_id=kb.id, doc_ids=doc_ids, tags=tags
    )
    # 过滤命中为空 → 直接返
    if (doc_ids or tags) and not candidate_doc_ids:
        return []

    if mode == "vector":
        hits = await _vector_search(
            session,
            kb=kb,
            query=query,
            top_k=top_k,
            doc_ids=candidate_doc_ids,
        )
    elif mode == "keyword":
        hits = await _keyword_search(
            session,
            kb_id=kb.id,
            query=query,
            top_k=top_k,
            doc_ids=candidate_doc_ids,
        )
    else:  # hybrid
        vec = await _vector_search(
            session,
            kb=kb,
            query=query,
            top_k=top_k * 2,
            doc_ids=candidate_doc_ids,
        )
        kw = await _keyword_search(
            session,
            kb_id=kb.id,
            query=query,
            top_k=top_k * 2,
            doc_ids=candidate_doc_ids,
        )
        hits = _rrf_merge(vec, kw, top_k=top_k)

    return [h for h in hits if h["score"] >= min_score][:top_k]


# ── search helpers ───────────────────────────────────────


async def _resolve_doc_filter(
    session: AsyncSession,
    *,
    kb_id: int,
    doc_ids: list[int] | None,
    tags: list[str] | None,
) -> set[int] | None:
    """返候选 doc_id 集；None 表示无过滤。"""
    if not tags and not doc_ids:
        return None
    candidate: set[int] | None = None
    if tags:
        stmt = select(Document.id).where(
            Document.kb_id == kb_id, Document.deleted_at.is_(None)
        )
        for t in tags:
            stmt = stmt.where(cast(Document.tags, JSONB).contains([t]))
        candidate = set((await session.execute(stmt)).scalars().all())
    if doc_ids:
        if candidate is None:
            candidate = set(doc_ids)
        else:
            candidate &= set(doc_ids)
    return candidate


async def _vector_search(
    session: AsyncSession,
    *,
    kb,
    query: str,
    top_k: int,
    doc_ids: set[int] | None,
) -> list[dict]:
    client = get_embedding_client(kb.embedding_model)
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
            Document.title,
            distance,
        )
        .join(Document, Chunk.doc_id == Document.id)
        .where(Chunk.kb_id == kb.id, Document.deleted_at.is_(None))
        .order_by(distance.asc())
        .limit(top_k)
    )
    if doc_ids is not None:
        stmt = stmt.where(Chunk.doc_id.in_(doc_ids))
    rows = (await session.execute(stmt)).all()
    return [
        {
            "chunk_id": r.id,
            "doc_id": r.doc_id,
            "seq": r.seq,
            "content": r.content,
            "score": 1.0 - float(r.distance),
            "document_title": r.title,
        }
        for r in rows
    ]


async def _keyword_search(
    session: AsyncSession,
    *,
    kb_id: int,
    query: str,
    top_k: int,
    doc_ids: set[int] | None,
) -> list[dict]:
    """PG ts_rank 关键词召回（simple 配置，无中文分词，按空格 / 标点切）"""
    # query → tsquery：用 plainto_tsquery 容错（自动 AND）
    ts_query = func.plainto_tsquery("simple", query)
    content_tsv = func.to_tsvector("simple", Chunk.content)
    # 用 content_tsv GENERATED 列加速
    # SQLAlchemy 不直接 reflect generated 列，引一个 raw column
    from sqlalchemy import literal_column
    tsv_col = literal_column("content_tsv")
    rank = func.ts_rank(tsv_col, ts_query).label("rank")
    stmt = (
        select(
            Chunk.id,
            Chunk.doc_id,
            Chunk.seq,
            Chunk.content,
            Document.title,
            rank,
        )
        .join(Document, Chunk.doc_id == Document.id)
        .where(
            Chunk.kb_id == kb_id,
            Document.deleted_at.is_(None),
            tsv_col.op("@@")(ts_query),
        )
        .order_by(rank.desc())
        .limit(top_k)
    )
    if doc_ids is not None:
        stmt = stmt.where(Chunk.doc_id.in_(doc_ids))
    rows = (await session.execute(stmt)).all()
    # 简单归一化到 [0, 1]：当前命中 rank 最大值归一
    if not rows:
        return []
    max_rank = max(float(r.rank) for r in rows) or 1.0
    # ts_rank 仅在内部排序用；归一化为 score 是粗略可解释化
    return [
        {
            "chunk_id": r.id,
            "doc_id": r.doc_id,
            "seq": r.seq,
            "content": r.content,
            "score": float(r.rank) / max_rank,
            "document_title": r.title,
        }
        for r in rows
    ]


def _rrf_merge(
    vec_hits: list[dict],
    kw_hits: list[dict],
    *,
    top_k: int,
    k: int = 60,
) -> list[dict]:
    """Reciprocal Rank Fusion：score = sum(1/(k + rank))"""
    rrf: dict[int, dict] = {}
    by_id: dict[int, dict] = {}
    for rank, h in enumerate(vec_hits):
        cid = h["chunk_id"]
        by_id[cid] = h
        rrf[cid] = rrf.get(cid, {"score": 0.0})
        rrf[cid]["score"] += 1.0 / (k + rank + 1)
    for rank, h in enumerate(kw_hits):
        cid = h["chunk_id"]
        by_id.setdefault(cid, h)
        rrf[cid] = rrf.get(cid, {"score": 0.0})
        rrf[cid]["score"] += 1.0 / (k + rank + 1)
    # 排序、归一化 score
    sorted_ids = sorted(rrf, key=lambda c: rrf[c]["score"], reverse=True)
    if not sorted_ids:
        return []
    max_score = rrf[sorted_ids[0]]["score"] or 1.0
    out: list[dict] = []
    for cid in sorted_ids[:top_k]:
        base = dict(by_id[cid])
        base["score"] = rrf[cid]["score"] / max_score
        out.append(base)
    return out


async def get_status(
    session: AsyncSession, *, kb_id: int, doc_id: int
) -> dict:
    """轮询 endpoint 用：返 doc 状态 + 进度（如果有关联 task）"""
    doc = await get_document(session, kb_id=kb_id, doc_id=doc_id)
    # 找最近的 ingest task
    task = (
        await session.execute(
            select(Task)
            .where(
                Task.task_type == "document_ingest",
                Task.ref_type == "document",
                Task.ref_id == doc.id,
            )
            .order_by(Task.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return {
        "document_id": doc.id,
        "status": doc.status,
        "progress": int(getattr(task, "progress", 0) or 0),
        "message": doc.status_message,
        "chunk_count": doc.chunk_count,
        "token_count": doc.token_count,
        "task_id": task.id if task else None,
    }


# ── 编排 helpers ─────────────────────────────────────────


async def _enqueue_ingest(
    session: AsyncSession,
    *,
    kb_id: int,
    doc_id: int,
) -> int:
    """落 task 行；调用方负责 commit + asyncio.create_task。"""
    task = Task(
        task_type="document_ingest",
        ref_type="document",
        ref_id=doc_id,
        status="queued",
        app_id=None,
    )
    session.add(task)
    await session.flush()
    return task.id


def spawn_ingest(*, task_id: int, document_id: int, kb_id: int) -> None:
    """在 session.commit() 后调用，把 ingest 投到 asyncio loop。"""
    asyncio.create_task(
        run_ingest_task(task_id=task_id, document_id=document_id, kb_id=kb_id)
    )
