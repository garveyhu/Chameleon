"""knowledge 模块业务编排

核心约束：
- KB 维度必须等于全局 inventory.embedding_dim()（v1 锁 1536）；
  不一致 → ValidationError fail-fast
- ingest 投到异步 worker（chameleon.api.knowledge.ingest.run_ingest_task）
- search 薄包装 chameleon.core.components.knowledge.search_kb（保单一数据路径）
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.knowledge.schemas import (
    CreateKbRequest,
    DocumentItem,
    IngestQueued,
    IngestRequest,
    KbItem,
    SearchHitItem,
    SearchRequest,
    UpdateDocumentRequest,
    UpdateKbRequest,
)
from chameleon.core.api.exceptions import (
    DocumentNotFoundError,
    KnowledgeBaseNotFoundError,
    ValidationError,
)
from chameleon.core.api.response import PageParams, PageResult
from chameleon.core.components.knowledge import search_kb
from chameleon.core.config import inventory
from chameleon.core.models import Chunk, Document, KnowledgeBase, Task
from chameleon.core.vector import get_store

# ── KB CRUD ─────────────────────────────────────────────


async def create_kb(
    session: AsyncSession,
    req: CreateKbRequest,
) -> KbItem:
    # 校验 kb_key 唯一
    existed = (
        await session.execute(
            select(KnowledgeBase.id).where(KnowledgeBase.kb_key == req.kb_key)
        )
    ).scalar_one_or_none()
    if existed:
        raise ValidationError(message=f"kb_key 已存在: {req.kb_key}")

    embedding_model = req.embedding_model or inventory.case_embedding()
    if not embedding_model:
        raise ValidationError(message="embedding_model 未指定且无全局 cases.embedding")

    cfg = inventory.embedding_model_config(embedding_model)
    dim = int(cfg.get("dim") or 0)
    global_dim = inventory.embedding_dim()
    if dim != global_dim:
        # v1 锁全局单维（裁决：与 chunks.embedding VECTOR(1536) 列严格一致）
        raise ValidationError(
            message=(
                f"embedding_model {embedding_model} dim={dim} "
                f"与全局维度 {global_dim} 不一致；v1 仅支持全局单维"
            )
        )

    row = KnowledgeBase(
        kb_key=req.kb_key,
        name=req.name,
        description=req.description,
        embedding_model=embedding_model,
        embedding_dim=dim,
        chunk_size=req.chunk_size,
        chunk_overlap=req.chunk_overlap,
        chunk_strategy=req.chunk_strategy
        or {
            "mode": "fixed",
            "chunk_size": req.chunk_size,
            "overlap": req.chunk_overlap,
        },
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    logger.info("kb created | kb_key={} | model={}", row.kb_key, embedding_model)
    return KbItem.model_validate(row)


async def update_kb(session: AsyncSession, kb_key: str, req: UpdateKbRequest) -> KbItem:
    row = await _get_kb_by_key(session, kb_key)
    if req.name is not None:
        row.name = req.name
    if req.description is not None:
        row.description = req.description
    if req.chunk_size is not None:
        row.chunk_size = req.chunk_size
    if req.chunk_overlap is not None:
        row.chunk_overlap = req.chunk_overlap
    if req.chunk_strategy is not None:
        row.chunk_strategy = req.chunk_strategy
    await session.flush()
    await session.refresh(row)
    return KbItem.model_validate(row)


async def delete_kb(session: AsyncSession, kb_key: str) -> KbItem:
    """软删 KB；不删 documents/chunks（v1 简化版，由 admin 手工清扫）"""
    row = await _get_kb_by_key(session, kb_key)
    row.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(row)
    logger.info("kb soft-deleted | kb_key={}", kb_key)
    return KbItem.model_validate(row)


async def list_kbs(session: AsyncSession, page: PageParams) -> PageResult[KbItem]:
    stmt = select(KnowledgeBase).where(KnowledgeBase.deleted_at.is_(None))
    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                stmt.order_by(KnowledgeBase.created_at.desc())
                .offset(page.offset)
                .limit(page.limit)
            )
        )
        .scalars()
        .all()
    )
    return PageResult(
        items=[KbItem.model_validate(r) for r in rows],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


# ── Documents ───────────────────────────────────────────


async def ingest_document(
    session: AsyncSession,
    kb_key: str,
    req: IngestRequest,
    *,
    app_id: str,
) -> tuple[IngestQueued, Document, KnowledgeBase]:
    """创建 documents + tasks 行；返 (响应 dto, doc, kb)

    调用方拿 doc + kb 后投 BackgroundTasks 跑 ingest worker。
    """
    kb = await _get_kb_by_key(session, kb_key)

    if req.source_type == "text" and not req.content:
        raise ValidationError(message="source_type=text 时 content 必填")
    if req.source_type == "url" and not req.source_uri:
        raise ValidationError(message="source_type=url 时 source_uri 必填")

    doc = Document(
        kb_id=kb.id,
        title=req.title,
        source_type=req.source_type,
        source_uri=req.source_uri,
        mime_type=req.mime_type,
        status="pending",
        meta={
            **(req.meta or {}),
            # text 内容暂时塞 meta（v1 简单方案；未来挪到 object store）
            **({"content": req.content} if req.source_type == "text" else {}),
        },
    )
    session.add(doc)
    await session.flush()

    task = Task(
        task_type="document_ingest",
        ref_type="document",
        ref_id=doc.id,
        status="queued",
        app_id=app_id,
    )
    session.add(task)
    await session.flush()
    await session.refresh(task)
    await session.refresh(doc)

    queued = IngestQueued(
        task_id=task.id,
        document_id=doc.id,
        status="queued",
    )
    logger.info(
        "ingest queued | kb={} | doc={} | task={}",
        kb_key,
        doc.id,
        task.id,
    )
    return queued, doc, kb


async def list_documents(
    session: AsyncSession,
    kb_key: str,
    page: PageParams,
) -> PageResult[DocumentItem]:
    kb = await _get_kb_by_key(session, kb_key)
    stmt = select(Document).where(
        Document.kb_id == kb.id, Document.deleted_at.is_(None)
    )
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
    return PageResult(
        items=[DocumentItem.model_validate(r) for r in rows],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


async def delete_document(
    session: AsyncSession, kb_key: str, doc_id: int
) -> DocumentItem:
    """软删 document + 同步删 chunks（向量数据无价值留）"""
    kb = await _get_kb_by_key(session, kb_key)
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

    # 删 chunks（物理）
    store = get_store()
    deleted_n = await store.delete(kb_id=kb.id, doc_id=doc_id)

    row.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(row)
    logger.info("document soft-deleted | doc={} | chunks_deleted={}", doc_id, deleted_n)
    return DocumentItem.model_validate(row)


async def get_document(
    session: AsyncSession, kb_key: str, doc_id: int
) -> DocumentItem:
    """取单篇文档详情。"""
    kb = await _get_kb_by_key(session, kb_key)
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
    return DocumentItem.model_validate(row)


async def update_document(
    session: AsyncSession, kb_key: str, doc_id: int, req: UpdateDocumentRequest
) -> DocumentItem:
    """改文档 title / tags / meta（不重分块）。"""
    kb = await _get_kb_by_key(session, kb_key)
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
    if req.title is not None:
        row.title = req.title
    if req.tags is not None:
        row.tags = req.tags
    if req.meta is not None:
        row.meta = req.meta
    row.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(row)
    return DocumentItem.model_validate(row)


# ── Search ──────────────────────────────────────────────


async def search(kb_key: str, req: SearchRequest) -> list[SearchHitItem]:
    hits = await search_kb(
        kb_key,
        req.query,
        top_k=req.top_k,
        min_score=req.min_score,
    )
    return [
        SearchHitItem(
            id=h.id,
            doc_id=h.doc_id,
            seq=h.seq,
            content=h.content,
            score=h.score,
            meta=h.meta,
        )
        for h in hits
    ]


# ── helpers ─────────────────────────────────────────────


async def _get_kb_by_key(session: AsyncSession, kb_key: str) -> KnowledgeBase:
    row = (
        await session.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.kb_key == kb_key,
                KnowledgeBase.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise KnowledgeBaseNotFoundError(message=f"知识库不存在: {kb_key}")
    return row


# 防 lint 误报：Chunk 在 ORM models 里被注册，本模块不直接 import
_ = Chunk
