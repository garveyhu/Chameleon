"""session_files admin HTTP 路由（/v1/admin/session-files）

观测域「会话文件管理」页用。支持分页 + 多条件查询 + 详情 + 删除（级联清 chunks
+ MinIO）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import PageParams, PageResult, Result
from chameleon.system.auth.dependencies import require_permission
from chameleon.core.infra.db import get_session
from chameleon.core.models import SessionFile

from . import service as sf_svc


class SessionFileItem(BaseModel):
    id: int
    session_id: str
    end_user_id: str | None
    object_url: str
    object_id: str
    filename: str
    mime: str
    size: int
    kind: str
    document_id: int | None
    ephemeral_kb_id: int | None
    status: str
    error: str | None
    created_at: str

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm(cls, row: SessionFile) -> "SessionFileItem":  # type: ignore[override]
        return cls(
            id=row.id,
            session_id=row.session_id,
            end_user_id=row.end_user_id,
            object_url=row.object_url,
            object_id=row.object_id,
            filename=row.filename,
            mime=row.mime,
            size=row.size,
            kind=row.kind,
            document_id=row.document_id,
            ephemeral_kb_id=row.ephemeral_kb_id,
            status=row.status,
            error=row.error,
            created_at=row.created_at.isoformat(),
        )


router = APIRouter(prefix="/v1/admin/session-files", tags=["admin:session-files"])


@router.get("", response_model=Result[PageResult[SessionFileItem]])
async def list_session_files(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session_id: str | None = Query(None, description="按会话过滤"),
    end_user_id: str | None = Query(None, description="按终端用户过滤"),
    kind: str | None = Query(
        None, description="image / audio / document / data / other"
    ),
    status: str | None = Query(
        None, description="uploaded / parsing / ready / failed"
    ),
    filename: str | None = Query(None, description="文件名关键字（ilike）"),
    db: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:read")),
) -> Result[PageResult[SessionFileItem]]:
    """会话文件列表 —— 分页 + 多条件查询"""
    res = await sf_svc.list_admin(
        db,
        page=PageParams(page=page, page_size=page_size),
        session_id=session_id,
        end_user_id=end_user_id,
        kind=kind,
        status=status,
        filename_kw=filename,
    )
    items = [SessionFileItem.from_orm(r) for r in res.items]
    return Result.ok(
        PageResult(items=items, total=res.total, page=res.page, page_size=res.page_size)
    )


class SessionFileDetail(SessionFileItem):
    """详情多带几条上下文（关联 session 标题 / 关联文档 / chunk 数量）"""

    session_title: str | None = None
    document_title: str | None = None
    chunk_count: int | None = None


@router.get("/{file_id}", response_model=Result[SessionFileDetail])
async def get_session_file(
    file_id: int,
    db: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:read")),
) -> Result[SessionFileDetail]:
    from sqlalchemy import select
    from chameleon.core.models import ChatSession, Document

    sf = await sf_svc.get_one(db, file_id)
    sess = (
        await db.execute(
            select(ChatSession).where(ChatSession.session_id == sf.session_id)
        )
    ).scalar_one_or_none()
    doc = await db.get(Document, sf.document_id) if sf.document_id else None
    chunk_count = doc.chunk_count if doc else None

    item = SessionFileDetail(
        **SessionFileItem.from_orm(sf).model_dump(),
        session_title=sess.title if sess else None,
        document_title=doc.title if doc else None,
        chunk_count=chunk_count,
    )
    return Result.ok(item)


@router.post("/{file_id}/delete", response_model=Result[dict])
async def delete_session_file(
    file_id: int,
    db: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:write")),
) -> Result[dict[str, Any]]:
    """删除会话文件 + 级联清相关资源（关联 Document 软删 / chunks 软删 / MinIO 异步删）"""
    await sf_svc.soft_delete(db, file_id)
    await db.commit()
    return Result.ok({"deleted": True})
