"""kbs admin HTTP 路由 (/v1/admin/kbs)

仅做 admin 视角的查看 + 元数据修改。业务方 CRUD 走 /v1/knowledge/*。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
)
from chameleon.core.api.response import PageParams, PageResult, Result
from chameleon.core.infra.db import get_session
from chameleon.core.models import Chunk, Document, KnowledgeBase
from chameleon.system.auth.dependencies import require_permission


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
    document_count: int = 0
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime


class ChunkItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    chunk_index: int = Field(default=0)
    content: str
    meta: dict | None = None
    created_at: datetime


class UpdateKbAdminRequest(BaseModel):
    name: str | None = None
    description: str | None = None


router = APIRouter(prefix="/v1/admin/kbs", tags=["admin:kbs"])


@router.get("", response_model=Result[PageResult[KbAdminItem]])
async def list_kbs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[PageResult[KbAdminItem]]:
    base = select(KnowledgeBase).where(KnowledgeBase.deleted_at.is_(None))
    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    kbs = (
        (
            await session.execute(
                base.order_by(KnowledgeBase.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    # 聚合 doc / chunk count
    items: list[KbAdminItem] = []
    for kb in kbs:
        doc_count = (
            await session.execute(
                select(func.count(Document.id)).where(
                    Document.kb_id == kb.id, Document.deleted_at.is_(None)
                )
            )
        ).scalar_one()
        chunk_count = (
            await session.execute(
                select(func.count(Chunk.id))
                .join(Document, Chunk.document_id == Document.id)
                .where(Document.kb_id == kb.id, Document.deleted_at.is_(None))
            )
        ).scalar_one()
        items.append(
            KbAdminItem(
                id=kb.id,
                kb_key=kb.kb_key,
                name=kb.name,
                description=kb.description,
                embedding_model=kb.embedding_model,
                embedding_dim=kb.embedding_dim,
                chunk_size=kb.chunk_size,
                chunk_overlap=kb.chunk_overlap,
                document_count=doc_count,
                chunk_count=chunk_count,
                created_at=kb.created_at,
                updated_at=kb.updated_at,
            )
        )

    return Result.ok(
        PageResult(items=items, total=total, page=page, page_size=page_size)
    )


@router.get("/{kb_id}", response_model=Result[KbAdminItem])
async def get_kb(
    kb_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[KbAdminItem]:
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
    return Result.ok(KbAdminItem.model_validate(kb))


@router.post("/{kb_id}/update", response_model=Result[KbAdminItem])
async def update_kb(
    kb_id: int,
    req: UpdateKbAdminRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:write")),
) -> Result[KbAdminItem]:
    kb = (
        await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
    ).scalar_one_or_none()
    if kb is None:
        raise BusinessError(
            ResultCode.KnowledgeBaseNotFound, message=f"kb 不存在: {kb_id}"
        )
    if req.name is not None:
        kb.name = req.name
    if req.description is not None:
        kb.description = req.description
    await session.flush()
    return Result.ok(KbAdminItem.model_validate(kb))


@router.get("/{kb_id}/chunks", response_model=Result[PageResult[ChunkItem]])
async def list_chunks(
    kb_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("kbs:read")),
) -> Result[PageResult[ChunkItem]]:
    base = (
        select(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.kb_id == kb_id, Document.deleted_at.is_(None))
    )
    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                base.order_by(Chunk.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return Result.ok(
        PageResult(
            items=[
                ChunkItem(
                    id=c.id,
                    document_id=c.document_id,
                    chunk_index=getattr(c, "chunk_index", 0),
                    content=c.content,
                    meta=getattr(c, "meta", None),
                    created_at=c.created_at,
                )
                for c in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
    )
