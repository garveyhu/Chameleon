"""kbs admin HTTP 路由 (/v1/admin/kbs)

KB 管理 + 文档全套 CRUD（Dify 量级）+ chunk 列表。
所有业务实现走 document_service；路由只做参数校验、调 service、包响应。
业务方 CRUD 仍走 /v1/knowledge/*；这里给 admin 用，按 kb_id 操作。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import PageParams, PageResult, Result
from chameleon.core.infra.db import get_session
from chameleon.system.audit_logs import write_audit_log
from chameleon.system.audit_logs.context import AuditContext, get_audit_context
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.kbs import (
    consistency as consistency_service,
)
from chameleon.system.kbs import (
    document_service,
    evaluation_service,
)

# ── DTO ────────────────────────────────────────────────────


class KbAdminItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kb_key: str
    name: str
    description: str | None = None
    embedding_model: str
    embedding_dim: int
    chunk_size: int
    chunk_overlap: int
    chunk_strategy: dict | None = None
    default_top_k: int = 5
    recall_mode: str = "vector"
    document_count: int = 0
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime


class ChunkItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doc_id: int
    seq: int
    content: str
    token_count: int | None = None
    meta: dict | None = None
    enabled: bool = True
    keywords: list | None = None
    hit_count: int = 0
    created_at: datetime


class UpdateChunkRequest(BaseModel):
    content: str | None = Field(default=None, max_length=20000)
    keywords: list[str] | None = None
    enabled: bool | None = None


class CreateKbAdminRequest(BaseModel):
    kb_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    embedding_model: str | None = None  # 不传走全局 cases.embedding（v1 单维）
    chunk_size: int = Field(default=800, ge=10, le=4000)
    chunk_overlap: int = Field(default=100, ge=0, le=500)
    chunk_strategy: dict | None = None


class UpdateKbAdminRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    chunk_strategy: dict | None = None
    default_top_k: int | None = Field(default=None, ge=1, le=50)
    recall_mode: str | None = Field(
        default=None, pattern="^(vector|hybrid|keyword)$"
    )


class DocumentAdminItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kb_id: int
    title: str
    source_type: str
    source_uri: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    status: str
    status_message: str | None = None
    chunk_count: int = 0
    token_count: int = 0
    enabled: bool = True
    tags: list = Field(default_factory=list)
    chunk_strategy: dict | None = None
    meta: dict | None = None
    created_at: datetime
    updated_at: datetime


class DocumentStatusItem(BaseModel):
    document_id: int
    status: str
    progress: int = 0
    message: str | None = None
    chunk_count: int = 0
    token_count: int = 0
    task_id: int | None = None


class IngestQueued(BaseModel):
    document_id: int
    task_id: int


class CreateUrlDocumentRequest(BaseModel):
    url: str
    name: str | None = None


class CreateTextDocumentRequest(BaseModel):
    name: str
    content: str


class UpdateDocumentRequest(BaseModel):
    tags: list[str] | None = None
    meta: dict | None = None
    chunk_strategy: dict | None = None
    enabled: bool | None = None


class BatchDocumentsRequest(BaseModel):
    action: str = Field(pattern="^(enable|disable|delete|reindex)$")
    doc_ids: list[int] = Field(min_length=1)


class BatchDocumentsResult(BaseModel):
    action: str
    affected: int
    queued: list[IngestQueued] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    doc_ids: list[int] | None = None
    tags: list[str] | None = None
    mode: str | None = Field(default=None, pattern="^(vector|hybrid|keyword)$")
    # v1.1 hit-test playground 开关（默认走 KB 配置 / 关闭）
    include_images: bool | None = None
    multi_query: int = Field(default=0, ge=0, le=5)
    hyde: bool = False


class SearchHitItem(BaseModel):
    chunk_id: int
    doc_id: int
    seq: int
    content: str
    score: float
    document_title: str
    # v1.1 B5/B6：多模态 + score 分项（UI 渲染留 Agent D）
    kind: str = "text"
    source_url: str | None = None
    vector_score: float | None = None
    bm25_score: float | None = None
    rerank_score: float | None = None


class EvalQuery(BaseModel):
    query: str
    expected_chunk_ids: list[int]


class CreateEvaluationRequest(BaseModel):
    name: str
    queries: list[EvalQuery]
    recall_mode: str = Field(
        default="vector", pattern="^(vector|hybrid|keyword)$"
    )
    top_k: int = Field(default=5, ge=1, le=50)


class EvaluationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kb_id: int
    name: str
    recall_mode: str
    top_k: int
    status: str
    error_message: str | None = None
    results: dict | None = None
    created_at: datetime
    completed_at: datetime | None = None


class EvaluationListItem(BaseModel):
    """列表用的瘦版本（不返巨大的 queries/results.per_query）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kb_id: int
    name: str
    recall_mode: str
    top_k: int
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    # 摘要指标（results 里的 metric 顶层）
    hit_at_5: float | None = None
    mrr: float | None = None
    latency_p50_ms: float | None = None


def _kb_to_item(kb, doc_count: int, chunk_count: int) -> KbAdminItem:
    return KbAdminItem(
        id=kb.id,
        kb_key=kb.kb_key,
        name=kb.name,
        description=kb.description,
        embedding_model=kb.embedding_model,
        embedding_dim=kb.embedding_dim,
        chunk_size=kb.chunk_size,
        chunk_overlap=kb.chunk_overlap,
        chunk_strategy=kb.chunk_strategy,
        default_top_k=kb.default_top_k,
        recall_mode=kb.recall_mode,
        document_count=doc_count,
        chunk_count=chunk_count,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


router = APIRouter(prefix="/v1/admin/kbs", tags=["admin:kbs"])


# ── KB 列表 / 详情 / 修改 ─────────────────────────────────


@router.post("", response_model=Result[KbAdminItem])
async def create_kb(
    req: CreateKbAdminRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[KbAdminItem]:
    kb = await document_service.create_kb(
        session,
        kb_key=req.kb_key,
        name=req.name,
        description=req.description,
        embedding_model=req.embedding_model,
        chunk_size=req.chunk_size,
        chunk_overlap=req.chunk_overlap,
        chunk_strategy=req.chunk_strategy,
    )
    await session.commit()
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="knowledge_base.create",
        resource_type="knowledge_base",
        resource_id=kb.id,
        after={"kb_key": kb.kb_key, "name": kb.name},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(_kb_to_item(kb, 0, 0))


@router.get("", response_model=Result[PageResult[KbAdminItem]])
async def list_kbs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[PageResult[KbAdminItem]]:
    paged, counts = await document_service.list_kbs_with_stats(
        session, PageParams(page=page, page_size=page_size)
    )
    items = [
        _kb_to_item(kb, dc, cc) for kb, (dc, cc) in zip(paged.items, counts)
    ]
    return Result.ok(
        PageResult(
            items=items, total=paged.total, page=paged.page, page_size=paged.page_size
        )
    )


@router.get("/{kb_id}", response_model=Result[KbAdminItem])
async def get_kb(
    kb_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[KbAdminItem]:
    kb, dc, cc = await document_service.get_kb_with_stats(session, kb_id)
    return Result.ok(_kb_to_item(kb, dc, cc))


@router.post("/{kb_id}/update", response_model=Result[KbAdminItem])
async def update_kb(
    kb_id: int,
    req: UpdateKbAdminRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[KbAdminItem]:
    kb = await document_service.update_kb(
        session,
        kb_id=kb_id,
        name=req.name,
        description=req.description,
        chunk_strategy=req.chunk_strategy,
        default_top_k=req.default_top_k,
        recall_mode=req.recall_mode,
    )
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="knowledge_base.update",
        resource_type="knowledge_base",
        resource_id=kb.id,
        after={"name": kb.name, "recall_mode": kb.recall_mode},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    _, dc, cc = await document_service.get_kb_with_stats(session, kb.id)
    return Result.ok(_kb_to_item(kb, dc, cc))


# ── P18.4 chunking 实时预览（不落库） ─────────────────────


class ChunkingPreviewRequest(BaseModel):
    """实时预览切块结果；不需 kb_id（KB 详情页可指定 KB 但本接口不依赖 KB）"""

    text: str = Field(..., min_length=1, max_length=200_000)
    strategy: dict = Field(default_factory=dict)


class ChunkPreviewItem(BaseModel):
    seq: int
    content: str
    char_count: int
    token_count_approx: int


class ChunkingPreviewResponse(BaseModel):
    mode: str
    count: int
    chunks: list[ChunkPreviewItem]


@router.post(
    "/chunking-preview", response_model=Result[ChunkingPreviewResponse]
)
async def chunking_preview(
    req: ChunkingPreviewRequest,
    _: object = Depends(require_permission("kbs:read")),
) -> Result[ChunkingPreviewResponse]:
    """对原文按 strategy 实时切块 —— 不落库，仅返结果

    支持 chunker.split 的全部 mode（fixed/paragraph/sentence/regex/token）。
    """
    from chameleon.api.knowledge import chunker
    from chameleon.core.api.exceptions import ValidationError

    try:
        chunks = chunker.split(req.text, req.strategy)
    except ValueError as e:
        raise ValidationError(message=str(e)) from e
    items = [
        ChunkPreviewItem(
            seq=i,
            content=c,
            char_count=len(c),
            token_count_approx=max(1, len(c) // 3),
        )
        for i, c in enumerate(chunks)
    ]
    return Result.ok(
        ChunkingPreviewResponse(
            mode=str(req.strategy.get("mode") or "fixed"),
            count=len(items),
            chunks=items,
        )
    )


# ── KB chunks 浏览（全 KB 维度） ──────────────────────────


@router.get("/{kb_id}/chunks", response_model=Result[PageResult[ChunkItem]])
async def list_kb_chunks(
    kb_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[PageResult[ChunkItem]]:
    paged = await document_service.list_kb_chunks(
        session, kb_id=kb_id, page=PageParams(page=page, page_size=page_size)
    )
    return Result.ok(
        PageResult(
            items=[ChunkItem.model_validate(c) for c in paged.items],
            total=paged.total,
            page=paged.page,
            page_size=paged.page_size,
        )
    )


# ── Documents：admin 全套 ─────────────────────────────────


@router.get(
    "/{kb_id}/documents", response_model=Result[PageResult[DocumentAdminItem]]
)
async def list_documents(
    kb_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = Query(None),
    tag: str | None = Query(None),
    sort_by: str = Query(
        "created_at", pattern="^(created_at|token_count|chunk_count)$"
    ),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[PageResult[DocumentAdminItem]]:
    _kb, paged = await document_service.list_documents(
        session,
        kb_id=kb_id,
        page=PageParams(page=page, page_size=page_size),
        status=status,
        tag=tag,
        sort_by=sort_by,
        order=order,
    )
    return Result.ok(
        PageResult(
            items=[DocumentAdminItem.model_validate(d) for d in paged.items],
            total=paged.total,
            page=paged.page,
            page_size=paged.page_size,
        )
    )


@router.get(
    "/{kb_id}/documents/{doc_id}", response_model=Result[DocumentAdminItem]
)
async def get_document(
    kb_id: int,
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[DocumentAdminItem]:
    row = await document_service.get_document(
        session, kb_id=kb_id, doc_id=doc_id
    )
    return Result.ok(DocumentAdminItem.model_validate(row))


@router.get(
    "/{kb_id}/documents/{doc_id}/status",
    response_model=Result[DocumentStatusItem],
)
async def get_document_status(
    kb_id: int,
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[DocumentStatusItem]:
    info = await document_service.get_status(
        session, kb_id=kb_id, doc_id=doc_id
    )
    return Result.ok(DocumentStatusItem.model_validate(info))


@router.post(
    "/{kb_id}/documents/upload", response_model=Result[list[IngestQueued]]
)
async def upload_documents(
    kb_id: int,
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[list[IngestQueued]]:
    """多文件上传；service 逐文件落 doc + 排 ingest。"""
    bundles = []  # (filename, bytes, content_type)
    for f in files:
        raw = await f.read()
        bundles.append((f.filename or "untitled", raw, f.content_type))
    queued = await document_service.create_upload_documents_bulk(
        session, kb_id=kb_id, bundles=bundles
    )
    await session.commit()
    for q in queued:
        document_service.spawn_ingest(
            task_id=q["task_id"], document_id=q["document_id"], kb_id=kb_id
        )
    return Result.ok([IngestQueued(**q) for q in queued])


@router.post(
    "/{kb_id}/documents/url", response_model=Result[IngestQueued]
)
async def create_url_document(
    kb_id: int,
    req: CreateUrlDocumentRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[IngestQueued]:
    doc_id, task_id = await document_service.create_url_document(
        session, kb_id=kb_id, url=req.url, name=req.name
    )
    await session.commit()
    document_service.spawn_ingest(
        task_id=task_id, document_id=doc_id, kb_id=kb_id
    )
    return Result.ok(IngestQueued(document_id=doc_id, task_id=task_id))


@router.post(
    "/{kb_id}/documents/text", response_model=Result[IngestQueued]
)
async def create_text_document(
    kb_id: int,
    req: CreateTextDocumentRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[IngestQueued]:
    doc_id, task_id = await document_service.create_text_document(
        session, kb_id=kb_id, name=req.name, content=req.content
    )
    await session.commit()
    document_service.spawn_ingest(
        task_id=task_id, document_id=doc_id, kb_id=kb_id
    )
    return Result.ok(IngestQueued(document_id=doc_id, task_id=task_id))


@router.post(
    "/{kb_id}/documents/{doc_id}/update",
    response_model=Result[DocumentAdminItem],
)
async def update_document(
    kb_id: int,
    doc_id: int,
    req: UpdateDocumentRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[DocumentAdminItem]:
    row = await document_service.update_document(
        session,
        kb_id=kb_id,
        doc_id=doc_id,
        tags=req.tags,
        meta=req.meta,
        chunk_strategy=req.chunk_strategy,
        enabled=req.enabled,
    )
    return Result.ok(DocumentAdminItem.model_validate(row))


@router.post(
    "/{kb_id}/documents/{doc_id}/reindex",
    response_model=Result[IngestQueued],
)
async def reindex_document(
    kb_id: int,
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[IngestQueued]:
    doc_id_out, task_id = await document_service.reindex_document(
        session, kb_id=kb_id, doc_id=doc_id
    )
    await session.commit()
    document_service.spawn_ingest(
        task_id=task_id, document_id=doc_id_out, kb_id=kb_id
    )
    return Result.ok(IngestQueued(document_id=doc_id_out, task_id=task_id))


@router.post(
    "/{kb_id}/reindex-all", response_model=Result[list[IngestQueued]]
)
async def reindex_all(
    kb_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[list[IngestQueued]]:
    queued = await document_service.reindex_all_documents(session, kb_id=kb_id)
    await session.commit()
    for q in queued:
        document_service.spawn_ingest(
            task_id=q["task_id"], document_id=q["document_id"], kb_id=kb_id
        )
    return Result.ok([IngestQueued(**q) for q in queued])


@router.post(
    "/{kb_id}/documents/{doc_id}/delete",
    response_model=Result[DocumentAdminItem],
)
async def delete_document(
    kb_id: int,
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[DocumentAdminItem]:
    row = await document_service.delete_document(
        session, kb_id=kb_id, doc_id=doc_id
    )
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="kb_document.delete",
        resource_type="kb_document",
        resource_id=doc_id,
        after={"kb_id": kb_id},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(DocumentAdminItem.model_validate(row))


@router.post(
    "/{kb_id}/documents/batch", response_model=Result[BatchDocumentsResult]
)
async def batch_documents(
    kb_id: int,
    req: BatchDocumentsRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[BatchDocumentsResult]:
    """批量启停 / 删除 / 重建文档。reindex 在 commit 后异步排队。"""
    if req.action in ("enable", "disable"):
        affected = await document_service.set_documents_enabled(
            session,
            kb_id=kb_id,
            doc_ids=req.doc_ids,
            enabled=req.action == "enable",
        )
        return Result.ok(
            BatchDocumentsResult(action=req.action, affected=affected)
        )

    if req.action == "delete":
        for doc_id in req.doc_ids:
            await document_service.delete_document(
                session, kb_id=kb_id, doc_id=doc_id
            )
        await write_audit_log(
            session,
            actor_user_id=audit.actor_user_id,
            actor_username=audit.actor_username,
            action="kb_document.batch_delete",
            resource_type="kb_document",
            resource_id=kb_id,
            after={"kb_id": kb_id, "doc_ids": req.doc_ids},
            ip=audit.ip,
            user_agent=audit.user_agent,
            request_id=audit.request_id,
        )
        return Result.ok(
            BatchDocumentsResult(action="delete", affected=len(req.doc_ids))
        )

    # reindex：先 commit 再异步排队（与单文档 reindex 一致）
    queued: list[IngestQueued] = []
    for doc_id in req.doc_ids:
        doc_id_out, task_id = await document_service.reindex_document(
            session, kb_id=kb_id, doc_id=doc_id
        )
        queued.append(IngestQueued(document_id=doc_id_out, task_id=task_id))
    await session.commit()
    for q in queued:
        document_service.spawn_ingest(
            task_id=q.task_id, document_id=q.document_id, kb_id=kb_id
        )
    return Result.ok(
        BatchDocumentsResult(
            action="reindex", affected=len(queued), queued=queued
        )
    )


# ── Document chunks（卡片墙用） ───────────────────────────


@router.get(
    "/{kb_id}/documents/{doc_id}/chunks",
    response_model=Result[PageResult[ChunkItem]],
)
async def list_document_chunks(
    kb_id: int,
    doc_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[PageResult[ChunkItem]]:
    _doc, paged = await document_service.list_document_chunks(
        session,
        kb_id=kb_id,
        doc_id=doc_id,
        page=PageParams(page=page, page_size=page_size),
    )
    return Result.ok(
        PageResult(
            items=[ChunkItem.model_validate(c) for c in paged.items],
            total=paged.total,
            page=paged.page,
            page_size=paged.page_size,
        )
    )


@router.post(
    "/{kb_id}/documents/{doc_id}/chunks/{chunk_id}/update",
    response_model=Result[ChunkItem],
)
async def update_chunk(
    kb_id: int,
    doc_id: int,
    chunk_id: int,
    req: UpdateChunkRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[ChunkItem]:
    chunk = await document_service.update_chunk(
        session,
        kb_id=kb_id,
        doc_id=doc_id,
        chunk_id=chunk_id,
        content=req.content,
        keywords=req.keywords,
        enabled=req.enabled,
    )
    await session.commit()
    return Result.ok(ChunkItem.model_validate(chunk))


@router.post(
    "/{kb_id}/documents/{doc_id}/chunks/{chunk_id}/delete",
    response_model=Result[None],
)
async def delete_chunk(
    kb_id: int,
    doc_id: int,
    chunk_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[None]:
    await document_service.delete_chunk(
        session, kb_id=kb_id, doc_id=doc_id, chunk_id=chunk_id
    )
    await session.commit()
    return Result.ok(None)


# ── KB search playground ──────────────────────────────────


@router.post(
    "/{kb_id}/search",
    response_model=Result[list[SearchHitItem]],
)
async def search_kb(
    kb_id: int,
    req: SearchRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[list[SearchHitItem]]:
    from chameleon.api.knowledge.hit_test import run_hit_test

    results = await run_hit_test(
        session,
        kb_id=kb_id,
        query=req.query,
        top_k=req.top_k,
        min_score=req.min_score,
        mode=req.mode,
        doc_ids=req.doc_ids,
        tags=req.tags,
        include_images=req.include_images,
        multi_query_count=req.multi_query,
        use_hyde=req.hyde,
    )
    return Result.ok([SearchHitItem(**r.to_dict()) for r in results])


# ── Retrieval Evaluations ─────────────────────────────────


def _eval_to_list_item(row) -> EvaluationListItem:
    res = row.results or {}
    hit5 = (res.get("hit_at_k") or {}).get("5")
    return EvaluationListItem(
        id=row.id,
        kb_id=row.kb_id,
        name=row.name,
        recall_mode=row.recall_mode,
        top_k=row.top_k,
        status=row.status,
        created_at=row.created_at,
        completed_at=row.completed_at,
        hit_at_5=hit5,
        mrr=res.get("mrr"),
        latency_p50_ms=res.get("latency_p50_ms"),
    )


@router.post(
    "/{kb_id}/evaluations",
    response_model=Result[EvaluationItem],
)
async def create_evaluation(
    kb_id: int,
    req: CreateEvaluationRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[EvaluationItem]:
    row = await evaluation_service.create_evaluation(
        session,
        kb_id=kb_id,
        name=req.name,
        queries=[q.model_dump() for q in req.queries],
        recall_mode=req.recall_mode,
        top_k=req.top_k,
    )
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="kb_evaluation.create",
        resource_type="kb_evaluation",
        resource_id=row.id,
        after={"kb_id": kb_id, "name": req.name},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    await session.commit()
    evaluation_service.spawn_eval(eval_id=row.id, kb_id=kb_id)
    return Result.ok(EvaluationItem.model_validate(row))


@router.get(
    "/{kb_id}/evaluations",
    response_model=Result[PageResult[EvaluationListItem]],
)
async def list_evaluations(
    kb_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[PageResult[EvaluationListItem]]:
    paged = await evaluation_service.list_evaluations(
        session, kb_id=kb_id, page=PageParams(page=page, page_size=page_size)
    )
    return Result.ok(
        PageResult(
            items=[_eval_to_list_item(r) for r in paged.items],
            total=paged.total,
            page=paged.page,
            page_size=paged.page_size,
        )
    )


@router.get(
    "/{kb_id}/evaluations/{eval_id}",
    response_model=Result[EvaluationItem],
)
async def get_evaluation(
    kb_id: int,
    eval_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[EvaluationItem]:
    row = await evaluation_service.get_evaluation(
        session, kb_id=kb_id, eval_id=eval_id
    )
    return Result.ok(EvaluationItem.model_validate(row))


@router.post(
    "/{kb_id}/evaluations/{eval_id}/delete",
    response_model=Result[EvaluationItem],
)
async def delete_evaluation(
    kb_id: int,
    eval_id: int,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[EvaluationItem]:
    row = await evaluation_service.delete_evaluation(
        session, kb_id=kb_id, eval_id=eval_id
    )
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="kb_evaluation.delete",
        resource_type="kb_evaluation",
        resource_id=eval_id,
        after={"kb_id": kb_id},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(EvaluationItem.model_validate(row))


# ── P20.3 collections admin ────────────────────────


from chameleon.system.kbs import collections_service as cs


@router.get(
    "/{kb_id}/collections",
    response_model=Result[list[cs.CollectionItem]],
)
async def list_collections(
    kb_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[list[cs.CollectionItem]]:
    return Result.ok(await cs.list_collections(session, kb_id))


@router.post(
    "/{kb_id}/collections",
    response_model=Result[cs.CollectionItem],
)
async def create_collection(
    kb_id: int,
    req: cs.CreateCollectionRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[cs.CollectionItem]:
    return Result.ok(await cs.create_collection(session, kb_id, req))


@router.post(
    "/{kb_id}/collections/{collection_id}/update",
    response_model=Result[cs.CollectionItem],
)
async def update_collection(
    kb_id: int,
    collection_id: int,
    req: cs.UpdateCollectionRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[cs.CollectionItem]:
    return Result.ok(
        await cs.update_collection(session, kb_id, collection_id, req)
    )


@router.post(
    "/{kb_id}/collections/{collection_id}/delete",
    response_model=Result[None],
)
async def delete_collection(
    kb_id: int,
    collection_id: int,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("kbs:delete")),
) -> Result[None]:
    await cs.delete_collection(session, kb_id, collection_id)
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="kb_collection.delete",
        resource_type="kb_collection",
        resource_id=collection_id,
        after={"kb_id": kb_id},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(None)


# ── KB-P5 元数据字段 admin ────────────────────────────────


from chameleon.system.kbs import metadata_service as ms


@router.get(
    "/{kb_id}/metadata-fields",
    response_model=Result[list[ms.MetadataFieldItem]],
)
async def list_metadata_fields(
    kb_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[list[ms.MetadataFieldItem]]:
    return Result.ok(await ms.list_fields(session, kb_id))


@router.post(
    "/{kb_id}/metadata-fields",
    response_model=Result[ms.MetadataFieldItem],
)
async def create_metadata_field(
    kb_id: int,
    req: ms.CreateMetadataFieldRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[ms.MetadataFieldItem]:
    return Result.ok(await ms.create_field(session, kb_id, req))


@router.post(
    "/{kb_id}/metadata-fields/{field_id}/delete",
    response_model=Result[None],
)
async def delete_metadata_field(
    kb_id: int,
    field_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[None]:
    await ms.delete_field(session, kb_id, field_id)
    return Result.ok(None)


# ── P21.3 一致性扫描 + 修复 ───────────────────────────────


class ConsistencyIssue(BaseModel):
    type: str
    chunk_id: int
    kb_id: int
    reason: str


class ConsistencyReportItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kb_id: int
    status: str
    issues: list[dict] | None = None
    scanned_count: int
    quarantined_count: int
    fixed_count: int
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


@router.post(
    "/{kb_id}/consistency-reports/scan",
    response_model=Result[ConsistencyReportItem],
)
async def scan_consistency(
    kb_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[ConsistencyReportItem]:
    """跑一次 KB 一致性扫描；标 quarantined + 落 report；不物理删"""
    report = await consistency_service.scan_kb(session, kb_id)
    return Result.ok(ConsistencyReportItem.model_validate(report))


@router.get(
    "/{kb_id}/consistency-reports",
    response_model=Result[list[ConsistencyReportItem]],
)
async def list_consistency_reports(
    kb_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[list[ConsistencyReportItem]]:
    reports = await consistency_service.list_reports(
        session, kb_id, limit=limit
    )
    return Result.ok(
        [ConsistencyReportItem.model_validate(r) for r in reports]
    )


@router.get(
    "/{kb_id}/consistency-reports/{report_id}",
    response_model=Result[ConsistencyReportItem],
)
async def get_consistency_report(
    kb_id: int,
    report_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[ConsistencyReportItem]:
    _ = kb_id  # 仅校验路径；service 内部按 report_id 查
    report = await consistency_service.get_report(session, report_id)
    return Result.ok(ConsistencyReportItem.model_validate(report))


@router.post(
    "/{kb_id}/consistency-reports/{report_id}/repair",
    response_model=Result[ConsistencyReportItem],
)
async def repair_consistency_report(
    kb_id: int,
    report_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[ConsistencyReportItem]:
    """物理删 quarantined chunks（红线：admin 显式确认才到这步）"""
    _ = kb_id
    report = await consistency_service.repair_report(session, report_id)
    return Result.ok(ConsistencyReportItem.model_validate(report))
