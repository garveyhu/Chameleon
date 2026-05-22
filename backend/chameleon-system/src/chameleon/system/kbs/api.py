"""kbs admin HTTP 路由 (/v1/admin/kbs)

KB 管理 + 文档全套 CRUD（Dify 量级）+ chunk 列表。
所有业务实现走 document_service；路由只做参数校验、调 service、包响应。
业务方 CRUD 仍走 /v1/knowledge/*；这里给 admin 用，按 kb_id 操作。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from chameleon.core.api.response import PageParams, PageResult, Result
from chameleon.core.infra.db import get_session
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.kbs import document_service
from sqlalchemy.ext.asyncio import AsyncSession


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
    created_at: datetime


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


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    doc_ids: list[int] | None = None
    tags: list[str] | None = None
    mode: str | None = Field(default=None, pattern="^(vector|hybrid|keyword)$")


class SearchHitItem(BaseModel):
    chunk_id: int
    doc_id: int
    seq: int
    content: str
    score: float
    document_title: str


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
    _, dc, cc = await document_service.get_kb_with_stats(session, kb.id)
    return Result.ok(_kb_to_item(kb, dc, cc))


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
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[PageResult[DocumentAdminItem]]:
    _kb, paged = await document_service.list_documents(
        session,
        kb_id=kb_id,
        page=PageParams(page=page, page_size=page_size),
        status=status,
        tag=tag,
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
    "/{kb_id}/documents/{doc_id}/delete",
    response_model=Result[DocumentAdminItem],
)
async def delete_document(
    kb_id: int,
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[DocumentAdminItem]:
    row = await document_service.delete_document(
        session, kb_id=kb_id, doc_id=doc_id
    )
    return Result.ok(DocumentAdminItem.model_validate(row))


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
    hits = await document_service.search_chunks(
        session,
        kb_id=kb_id,
        query=req.query,
        top_k=req.top_k,
        min_score=req.min_score,
        doc_ids=req.doc_ids,
        tags=req.tags,
    )
    return Result.ok([SearchHitItem(**h) for h in hits])
