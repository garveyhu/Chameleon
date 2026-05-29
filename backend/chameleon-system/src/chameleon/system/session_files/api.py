"""session_files admin HTTP 路由（/v1/admin/session-files）

观测域「会话文件管理」页用。支持分页 + 多条件查询 + 详情 + 内嵌预览 + 删除（级联清 chunks
+ MinIO）。

预览路由：按 kind / mime 决定怎么给前端：
- text：直接给文本内容（parsed_text 或 MinIO 原始 bytes 解码）
- image / pdf：返 presigned GET URL 让前端 <img> / <iframe>
- office：返 parsed_text（解析后的纯文本，避免乱码）
- download_only：返 presigned URL 让前端给"下载"按钮
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from loguru import logger
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import PageParams, PageResult, Result
from chameleon.data.infra.db import get_session
from chameleon.data.infra.object_store import get_object_store
from chameleon.data.models import ChatSession, SessionFile, SessionFileChunk
from chameleon.system.auth.dependencies import require_permission

from . import service as sf_svc

# ── 预览相关 ───────────────────────────────────────────────


_PreviewKind = Literal["text", "image", "pdf", "office", "audio", "download_only"]

# 文本类 mime 白名单 —— 这些可以直接给前端等宽显示
_TEXT_MIMES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/html",
    "text/xml",
    "text/x-python",
    "text/javascript",
    "text/typescript",
    "application/json",
    "application/xml",
    "application/x-yaml",
    "application/yaml",
}

# 解析后能转纯文本的 office 类（已经在 parsed_text 里）
_OFFICE_MIMES = {
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/rtf",
    "application/epub+zip",
}

_PREVIEW_TEXT_LIMIT = 200_000  # 前端预览最多展 20W 字符（小文件全文 80K 阈值的 2.5x 兜底）


def _classify_preview_kind(mime: str) -> _PreviewKind:
    m = (mime or "").lower()
    if m.startswith("image/"):
        return "image"
    if m == "application/pdf":
        return "pdf"
    if m.startswith("audio/"):
        return "audio"
    if m in _TEXT_MIMES or m.startswith("text/"):
        return "text"
    if m in _OFFICE_MIMES:
        return "office"
    return "download_only"


# ── Schema ─────────────────────────────────────────────────


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
    text_size: int | None
    use_full_text: bool
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
            text_size=row.text_size,
            use_full_text=row.use_full_text,
            status=row.status,
            error=row.error,
            created_at=row.created_at.isoformat(),
        )


class SessionFileDetail(SessionFileItem):
    """详情多带：关联 session 标题 + chunk 数量（大文件切块情况）"""

    session_title: str | None = None
    chunk_count: int = 0


class PreviewResponse(BaseModel):
    kind: _PreviewKind
    mime: str
    filename: str
    size: int
    text: str | None = None
    url: str | None = None  # presigned GET URL（image/pdf/audio/download_only）
    truncated: bool = False
    note: str | None = None  # 异常 / 提示信息（如解析失败 / 文件过大）


router = APIRouter(prefix="/v1/admin/session-files", tags=["admin:session-files"])


# ── 列表 / 详情 / 预览 / 删除 ─────────────────────────────────


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
        None, description="uploaded / parsing / indexing / ready / failed"
    ),
    filename: str | None = Query(None, description="文件名关键字（ilike）"),
    since: datetime | None = Query(None, description="ISO8601 起始（含）"),
    until: datetime | None = Query(None, description="ISO8601 结束（含）"),
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
        since=since,
        until=until,
    )
    items = [SessionFileItem.from_orm(r) for r in res.items]
    return Result.ok(
        PageResult(items=items, total=res.total, page=res.page, page_size=res.page_size)
    )


@router.get("/{file_id}", response_model=Result[SessionFileDetail])
async def get_session_file(
    file_id: int,
    db: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:read")),
) -> Result[SessionFileDetail]:
    sf = await sf_svc.get_one(db, file_id)
    sess = (
        await db.execute(
            select(ChatSession).where(ChatSession.session_id == sf.session_id)
        )
    ).scalar_one_or_none()
    chunk_count = (
        await db.execute(
            select(sa_func.count(SessionFileChunk.id)).where(
                SessionFileChunk.session_file_id == sf.id,
                SessionFileChunk.deleted_at.is_(None),
            )
        )
    ).scalar_one()
    item = SessionFileDetail(
        **SessionFileItem.from_orm(sf).model_dump(),
        session_title=sess.title if sess else None,
        chunk_count=int(chunk_count),
    )
    return Result.ok(item)


@router.get("/{file_id}/preview", response_model=Result[PreviewResponse])
async def preview_session_file(
    file_id: int,
    db: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:read")),
) -> Result[PreviewResponse]:
    """内嵌预览端点 —— 按 kind / mime 决定给文本 / presigned URL，避免前端跳新页乱码。"""
    sf = await sf_svc.get_one(db, file_id)
    kind = _classify_preview_kind(sf.mime)
    store = get_object_store()

    # 图片 / PDF / 音频 / 其他二进制 → 直接给 presigned URL，前端用 img/iframe/audio/下载
    if kind in ("image", "pdf", "audio", "download_only"):
        try:
            url = store.presigned_get_url(sf.object_id, expires_seconds=3600)
        except Exception as e:  # noqa: BLE001
            logger.warning("presign get failed: {}", e)
            url = sf.object_url
        return Result.ok(
            PreviewResponse(
                kind=kind,
                mime=sf.mime,
                filename=sf.filename,
                size=sf.size,
                url=url,
            )
        )

    # 文本 / Office → 优先 parsed_text；没有则尝试从 MinIO 抓原始 bytes 解码
    text: str | None = sf.parsed_text
    note: str | None = None
    if not text:
        if sf.status == "failed":
            note = sf.error or "文件解析失败"
        elif sf.status in ("parsing", "indexing"):
            note = "正在解析中，请稍后刷新"
        elif sf.use_full_text is False:
            # 大文件切块路径：parsed_text 为空是正常的（没存全文），尝试读 MinIO
            try:
                raw = store.get(sf.object_id)
                text = raw.decode("utf-8", errors="replace")
            except Exception as e:  # noqa: BLE001
                logger.warning("MinIO 读取失败 {}: {}", sf.object_id, e)
                note = "源文件不可读"

    truncated = False
    if text and len(text) > _PREVIEW_TEXT_LIMIT:
        text = text[:_PREVIEW_TEXT_LIMIT]
        truncated = True

    return Result.ok(
        PreviewResponse(
            kind=kind,
            mime=sf.mime,
            filename=sf.filename,
            size=sf.size,
            text=text,
            truncated=truncated,
            note=note,
        )
    )


@router.post("/{file_id}/delete", response_model=Result[dict])
async def delete_session_file(
    file_id: int,
    db: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:write")),
) -> Result[dict[str, Any]]:
    """删除会话文件 + 级联清相关资源（chunks 软删 / MinIO 异步删）"""
    await sf_svc.soft_delete(db, file_id)
    await db.commit()
    return Result.ok({"deleted": True})
