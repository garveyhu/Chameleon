"""admin 视角的 KB 文档管理服务

业务方走 chameleon-api 的 /v1/knowledge/*；本模块给 admin 用，
直接以 kb_id 操作，覆盖完整 Dify 级 CRUD + ingest 编排。
"""

from __future__ import annotations

import asyncio
import mimetypes
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import cast, func, select, update
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
from chameleon.core.vector import get_store
from chameleon.data.models import Chunk, Document, KnowledgeBase, Task
from chameleon.data.utils.snowflake import next_id

# ── KB 创建（复用业务层 create_kb：kb_key 唯一 + embedding 维度校验） ──


async def create_kb(
    session: AsyncSession,
    *,
    kb_key: str,
    name: str,
    description: str | None = None,
    embedding_model: str | None = None,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
    chunk_strategy: dict | None = None,
) -> KnowledgeBase:
    from chameleon.api.knowledge.schemas import CreateKbRequest
    from chameleon.api.knowledge.service import create_kb as _biz_create_kb

    item = await _biz_create_kb(
        session,
        CreateKbRequest(
            kb_key=kb_key,
            name=name,
            description=description,
            embedding_model=embedding_model,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            chunk_strategy=chunk_strategy,
        ),
    )
    return await _get_kb(session, item.id)


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
    icon: str | None = None,
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
    if icon is not None:
        kb.icon = icon or None  # 传空串 = 清除图标
    if chunk_strategy is not None:
        kb.chunk_strategy = chunk_strategy
    if default_top_k is not None:
        kb.default_top_k = default_top_k
    if recall_mode is not None:
        kb.recall_mode = recall_mode
    await session.flush()
    await session.refresh(kb)
    return kb


async def delete_kb(session: AsyncSession, *, kb_id: int) -> None:
    """彻底删除 KB 及其所有关联数据。

    硬删 knowledge_bases 行 → DB 级联（各关联表 kb_id FK 均 ondelete=CASCADE）
    清掉 documents / chunks（向量）/ kb_metadata_fields / retrieval_evaluation /
    kb_consistency_reports / kb_collections / agent_kb_link。
    DB 级联管不到的 MinIO 上传对象在此显式删除（best-effort）。
    """
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

    # 删 MinIO 上传对象（含已软删文档，按 source_uri 收集）
    upload_uris = (
        (
            await session.execute(
                select(Document.source_uri).where(
                    Document.kb_id == kb_id,
                    Document.source_type == "upload",
                    Document.source_uri.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for uri in upload_uris:
        try:
            storage.delete_upload(uri)
        except Exception:  # noqa: BLE001
            logger.exception("delete object failed: {}", uri)

    # 硬删 KB 行 → DB 级联清所有关联表
    await session.delete(kb)
    await session.flush()
    logger.info("kb deleted | kb={} | objects={}", kb_id, len(upload_uris))


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

    # B5：图片上传标 kind=image，ingest 走 caption → 文本向量 流程
    doc_kind = "image" if (mime or "").startswith("image/") else "text"
    doc = Document(
        id=doc_id,
        kb_id=kb.id,
        title=filename,
        source_type="upload",
        source_uri=object_key,
        mime_type=mime,
        kind=doc_kind,
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


#: 列表可排序列白名单（前端传 sort_by → ORM 列）
_DOC_SORT_COLUMNS = {
    "created_at": Document.created_at,
    "token_count": Document.token_count,
    "chunk_count": Document.chunk_count,
}


async def list_documents(
    session: AsyncSession,
    *,
    kb_id: int,
    page: PageParams,
    status: str | None = None,
    tag: str | None = None,
    sort_by: str = "created_at",
    order: str = "desc",
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
    sort_col = _DOC_SORT_COLUMNS.get(sort_by, Document.created_at)
    sort_expr = sort_col.asc() if order == "asc" else sort_col.desc()
    rows = (
        (
            await session.execute(
                stmt.order_by(sort_expr, Document.id.desc())
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
    enabled: bool | None = None,
) -> Document:
    """更新 document tag / metadata / chunk_strategy / 启停；不重新分块。"""
    row = await get_document(session, kb_id=kb_id, doc_id=doc_id)
    if tags is not None:
        row.tags = list(tags)
    if meta is not None:
        row.meta = {**(row.meta or {}), **meta}
    if chunk_strategy is not None:
        row.chunk_strategy = chunk_strategy
    if enabled is not None:
        row.enabled = enabled
    await session.flush()
    await session.refresh(row)
    return row


async def set_documents_enabled(
    session: AsyncSession, *, kb_id: int, doc_ids: list[int], enabled: bool
) -> int:
    """批量启停文档；返回受影响行数。"""
    if not doc_ids:
        return 0
    result = await session.execute(
        update(Document)
        .where(
            Document.kb_id == kb_id,
            Document.id.in_(doc_ids),
            Document.deleted_at.is_(None),
        )
        .values(enabled=enabled)
    )
    await session.flush()
    return int(result.rowcount or 0)


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
    await session.refresh(row)
    return row


async def list_document_chunks(
    session: AsyncSession,
    *,
    kb_id: int,
    doc_id: int,
    page: PageParams,
    q: str | None = None,
) -> tuple[Document, PageResult[Chunk]]:
    """分页查询某 doc 的 chunks（按 seq 升序）；q 非空时按内容子串过滤"""
    doc = await get_document(session, kb_id=kb_id, doc_id=doc_id)
    stmt = select(Chunk).where(Chunk.doc_id == doc.id)
    if q and q.strip():
        stmt = stmt.where(Chunk.content.ilike(f"%{q.strip()}%"))
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


# ── 段落级管理（KB-P3：编辑 / 删除 / 启停） ──────────────────


async def _get_chunk(
    session: AsyncSession, *, kb_id: int, doc_id: int, chunk_id: int
) -> Chunk:
    chunk = (
        await session.execute(
            select(Chunk).where(
                Chunk.id == chunk_id,
                Chunk.doc_id == doc_id,
                Chunk.kb_id == kb_id,
            )
        )
    ).scalar_one_or_none()
    if chunk is None:
        raise ValidationError(message=f"切块不存在: {chunk_id}")
    return chunk


async def update_chunk(
    session: AsyncSession,
    *,
    kb_id: int,
    doc_id: int,
    chunk_id: int,
    content: str | None = None,
    keywords: list | None = None,
    enabled: bool | None = None,
) -> Chunk:
    """编辑切块：改内容则重嵌向量；可改关键词 / 启停。"""
    chunk = await _get_chunk(session, kb_id=kb_id, doc_id=doc_id, chunk_id=chunk_id)
    if content is not None and content.strip() and content != chunk.content:
        from chameleon.core.embedding import get_embedding_client
        from chameleon.data.utils.tokenizer import approx_tokens

        kb = await _get_kb(session, kb_id)
        embedder = get_embedding_client(kb.embedding_model)
        vecs = await embedder.embed([content])
        if vecs:
            chunk.embedding = vecs[0]
        chunk.content = content
        chunk.token_count = approx_tokens(content)  # 与 ingest 同一口径
    if keywords is not None:
        chunk.keywords = keywords
    if enabled is not None:
        chunk.enabled = enabled
    await session.flush()
    await session.refresh(chunk)
    return chunk


async def delete_chunk(
    session: AsyncSession, *, kb_id: int, doc_id: int, chunk_id: int
) -> None:
    chunk = await _get_chunk(session, kb_id=kb_id, doc_id=doc_id, chunk_id=chunk_id)
    await session.delete(chunk)
    doc = await get_document(session, kb_id=kb_id, doc_id=doc_id)
    doc.chunk_count = max(0, (doc.chunk_count or 0) - 1)
    await session.flush()


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
    metadata_filters: dict[str, str] | None = None,
    mode: str | None = None,
) -> list[dict]:
    """三模式 chunk 检索；可按 doc_ids / tags / metadata 过滤。

    薄委托 api.knowledge.hit_test.run_hit_test（单一检索路径：hybrid RRF /
    过滤 quarantined / multi-query / HyDE / reranker / score breakdown）。
    mode: vector / keyword / hybrid（None 时走 kb.recall_mode）
    返 [{chunk_id, doc_id, seq, content, score, document_title, kind,
        source_url, vector_score, bm25_score, rerank_score}]
    """
    from chameleon.api.knowledge.hit_test import run_hit_test

    results = await run_hit_test(
        session,
        kb_id=kb_id,
        query=query,
        top_k=top_k,
        min_score=min_score,
        mode=mode,
        doc_ids=doc_ids,
        tags=tags,
        metadata_filters=metadata_filters,
    )
    return [r.to_dict() for r in results]


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
