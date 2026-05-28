"""SessionFile service（Phase B 临时 RAG）

职责：
1. 记录 session ↔ 文件的关联（SessionFile 行）
2. document 类型：复用 KB ingest pipeline 切块入会话的 ephemeral_kb
3. 提供查询 / 软删 / 级联清理

约定：
- 同一 session 的所有 document SessionFile 共享一个 ephemeral_kb（懒建）
- ephemeral_kb.kind = 'ephemeral_session'，name = f'临时 KB · {session_id}'
- ephemeral_kb 不出现在常规 KB 列表（按 kind 过滤）
"""

from __future__ import annotations

import asyncio
import secrets
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.api.response import PageParams, PageResult
from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.infra.object_store import get_object_store
from chameleon.core.models import Chunk, Document, KnowledgeBase, SessionFile
from chameleon.system.kbs import document_service as kb_doc_service


# ── kind 分类（widget 端 classifyKind 的镜像，后端兜底） ─────────


_DOC_MIMES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/epub+zip",
    "application/rtf",
    "application/xml",
    "application/xhtml+xml",
    "application/json",
    "message/rfc822",
    "application/vnd.ms-outlook",
}
_DATA_MIMES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def classify_kind(mime: str) -> str:
    m = (mime or "").lower()
    if m.startswith("image/"):
        return "image"
    if m.startswith("audio/"):
        return "audio"
    if m.startswith("video/"):
        return "other"  # 视频暂不参与多模态 / RAG（仅保留 URL）
    if m in _DATA_MIMES:
        return "data"
    if m.startswith("text/") or m in _DOC_MIMES:
        return "document"
    return "other"


# ── ephemeral KB 取/建 ──────────────────────────────────────


async def _ensure_ephemeral_kb(
    session: AsyncSession, *, session_id: str, embedding_model: str | None = None
) -> KnowledgeBase:
    """会话第一次需要 ephemeral KB 时懒建；后续复用同一个。"""
    # 找现有
    existing = (
        await session.execute(
            select(SessionFile.ephemeral_kb_id)
            .where(
                SessionFile.session_id == session_id,
                SessionFile.ephemeral_kb_id.is_not(None),
                SessionFile.deleted_at.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing:
        kb = (
            await session.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == existing, KnowledgeBase.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        if kb is not None:
            return kb

    # 新建 —— kb_key 加随机串避免软删后重建冲突 unique
    salt = secrets.token_hex(4)
    kb_key = f"eph_{session_id}_{salt}"
    name = f"临时 KB · {session_id}"
    kb = await kb_doc_service.create_kb(
        session,
        kb_key=kb_key,
        name=name,
        description="会话临时知识库（attachments 上传时自动建）",
        embedding_model=embedding_model,
    )
    # 切到 ephemeral_session kind
    await session.execute(
        update(KnowledgeBase)
        .where(KnowledgeBase.id == kb.id)
        .values(kind="ephemeral_session")
    )
    await session.flush()
    return await session.get(KnowledgeBase, kb.id)  # type: ignore[return-value]


# ── 记录 SessionFile：所有附件都落这张表（含图/音/文档/数据） ─────


async def record_attachments(
    session: AsyncSession,
    *,
    session_id: str,
    end_user_id: str | None,
    attachments: list[dict[str, Any]],
) -> list[SessionFile]:
    """把 attachments 落库 + 触发 document 类型异步解析。返回 SessionFile 行列表。

    调用方在 invoke 流程里调用：图/音类型仅记账；document/data 类型记账 + 排
    ephemeral KB ingest（后台跑）。
    """
    if not attachments:
        return []

    # 去重：finalize 端点和 invoke 都会调本函数（widget 上传立刻 record + 发消息再透
    # attachments）；按 (session_id, object_id) 拒绝重复 INSERT。
    incoming_oids = [
        (a.get("object_id") or _extract_object_id_from_url(a.get("object_url") or ""))
        for a in attachments
    ]
    existing = set(
        (
            await session.execute(
                select(SessionFile.object_id).where(
                    SessionFile.session_id == session_id,
                    SessionFile.object_id.in_([o for o in incoming_oids if o]),
                    SessionFile.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    rows: list[SessionFile] = []
    kb_for_docs: KnowledgeBase | None = None

    for att in attachments:
        mime = att.get("mime") or "application/octet-stream"
        kind = classify_kind(mime)
        object_url = att.get("object_url") or ""
        object_id = att.get("object_id") or _extract_object_id_from_url(object_url)
        if object_id and object_id in existing:
            continue  # 已经在表里（finalize 阶段插过）→ 跳过避免重复
        sf = SessionFile(
            session_id=session_id,
            end_user_id=end_user_id,
            object_url=object_url,
            object_id=object_id,
            filename=att.get("filename") or "unknown",
            mime=mime,
            size=int(att.get("size") or 0),
            kind=kind,
            status="ready" if kind in ("image", "audio") else "uploaded",
        )
        session.add(sf)
        rows.append(sf)

    if not rows:
        return []
    await session.flush()

    # document/data 类型：懒建 ephemeral_kb + 触发 ingest
    doc_rows = [r for r in rows if r.kind in ("document", "data")]
    if doc_rows:
        kb_for_docs = await _ensure_ephemeral_kb(session, session_id=session_id)
        for sf in doc_rows:
            sf.ephemeral_kb_id = kb_for_docs.id
            sf.status = "parsing"
        await session.flush()
        # 异步 ingest（不阻塞响应路径）
        for sf in doc_rows:
            asyncio.create_task(_async_ingest_session_file(sf.id))

    return rows


def _extract_object_id_from_url(url: str) -> str:
    """从 presigned URL 反推 object_id（MinIO path 后段）"""
    try:
        parts = urlparse(url).path.lstrip("/").split("/", 1)
        return parts[1] if len(parts) == 2 else parts[0]
    except Exception:  # noqa: BLE001
        return ""


# ── 异步 ingest：下载 → create_upload_document → KB pipeline 接管 ────


async def _async_ingest_session_file(session_file_id: int) -> None:
    """独立 session 跑，避免阻塞 invoke 路径。失败更新 status='failed'。"""
    async with AsyncSessionLocal() as db:
        sf = await db.get(SessionFile, session_file_id)
        if sf is None or sf.ephemeral_kb_id is None:
            return
        try:
            # 下载 MinIO object bytes（widget 已经传上去了）
            content = _download_object_bytes(sf.object_url, sf.object_id)
            doc_id, _task_id = await kb_doc_service.create_upload_document(
                db,
                kb_id=sf.ephemeral_kb_id,
                filename=sf.filename,
                content=content,
                content_type=sf.mime,
            )
            sf.document_id = doc_id
            # status 由 ingest task 异步更新到 Document.status；前端轮询 SessionFile.status
            # 同时这里把 SessionFile.status 跟 Document.status 联动
            await db.commit()
            # 触发完整 ingest pipeline（自带切块/向量化/落 chunks）
            from chameleon.api.knowledge.ingest import run_ingest_task

            try:
                await run_ingest_task(
                    task_id=_task_id, document_id=doc_id, kb_id=sf.ephemeral_kb_id
                )
                sf = await db.get(SessionFile, session_file_id)
                if sf:
                    sf.status = "ready"
                    await db.commit()
            except Exception as e:  # noqa: BLE001
                logger.warning("ephemeral ingest 失败 sf={} err={}", session_file_id, e)
                sf = await db.get(SessionFile, session_file_id)
                if sf:
                    sf.status = "failed"
                    sf.error = str(e)[:500]
                    await db.commit()
        except Exception as e:  # noqa: BLE001
            logger.exception("ephemeral ingest 顶层失败 sf={}", session_file_id)
            sf = await db.get(SessionFile, session_file_id)
            if sf:
                sf.status = "failed"
                sf.error = str(e)[:500]
                await db.commit()


def _download_object_bytes(object_url: str, object_id: str) -> bytes:
    """优先从 MinIO 直读（API 内部网络快）；失败回退 presigned GET。"""
    store = get_object_store()
    try:
        if object_id:
            return store.get(object_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("MinIO 直读失败，回退 HTTP GET: {}", e)
    # 回退：用 presigned GET URL
    resp = httpx.get(object_url, timeout=30.0)
    resp.raise_for_status()
    return resp.content


# ── 列表 / 详情 / 删除 ───────────────────────────────────────


async def list_for_session(
    db: AsyncSession,
    *,
    session_id: str,
    end_user_id: str | None = None,
) -> list[SessionFile]:
    """按 session_id（+ end_user_id 隔离）列附件，按 created_at desc。"""
    q = select(SessionFile).where(
        SessionFile.session_id == session_id, SessionFile.deleted_at.is_(None)
    )
    if end_user_id is not None:
        q = q.where(SessionFile.end_user_id == end_user_id)
    q = q.order_by(SessionFile.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def list_admin(
    db: AsyncSession,
    *,
    page: PageParams,
    session_id: str | None = None,
    end_user_id: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    filename_kw: str | None = None,
) -> PageResult[SessionFile]:
    """admin 视角分页 + 多条件查询"""
    base = select(SessionFile).where(SessionFile.deleted_at.is_(None))
    if session_id:
        base = base.where(SessionFile.session_id == session_id)
    if end_user_id:
        base = base.where(SessionFile.end_user_id == end_user_id)
    if kind:
        base = base.where(SessionFile.kind == kind)
    if status:
        base = base.where(SessionFile.status == status)
    if filename_kw:
        base = base.where(SessionFile.filename.ilike(f"%{filename_kw}%"))

    from sqlalchemy import func as sa_func

    total = (
        await db.execute(
            select(sa_func.count()).select_from(base.subquery())
        )
    ).scalar_one()
    items = (
        (
            await db.execute(
                base.order_by(SessionFile.created_at.desc())
                .offset((page.page - 1) * page.page_size)
                .limit(page.page_size)
            )
        )
        .scalars()
        .all()
    )
    return PageResult(items=list(items), total=int(total), page=page.page, page_size=page.page_size)


async def get_one(db: AsyncSession, file_id: int) -> SessionFile:
    sf = await db.get(SessionFile, file_id)
    if sf is None or sf.deleted_at is not None:
        raise BusinessError(ResultCode.NotFound, message=f"附件不存在: {file_id}")
    return sf


async def soft_delete(db: AsyncSession, file_id: int) -> None:
    """软删 SessionFile + 级联清 Document/chunks + MinIO object（后台异步）"""
    from datetime import datetime, timezone

    sf = await get_one(db, file_id)
    sf.deleted_at = datetime.now(timezone.utc)

    # 级联：document_id 关联的 KB Document 也软删（chunks 由 KB pipeline 处理）
    if sf.document_id:
        doc = await db.get(Document, sf.document_id)
        if doc is not None and doc.deleted_at is None:
            doc.deleted_at = datetime.now(timezone.utc)
            # chunks 同样软删（KB-D 一致性扫描会清向量索引）
            await db.execute(
                update(Chunk)
                .where(Chunk.document_id == doc.id, Chunk.deleted_at.is_(None))
                .values(deleted_at=datetime.now(timezone.utc))
            )

    await db.flush()

    # MinIO 异步删（避免阻塞 HTTP）
    asyncio.create_task(_async_delete_minio(sf.object_id))


async def _async_delete_minio(object_id: str) -> None:
    if not object_id:
        return
    try:
        store = get_object_store()
        store.delete(object_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("MinIO 删除失败（不影响业务）: {} err={}", object_id, e)


# ── ephemeral RAG 注入（agent.service 调） ─────────────────


async def resolve_ephemeral_kb_id(db: AsyncSession, session_id: str) -> int | None:
    """当前 session 是否有 ready 的 ephemeral KB（有 document SessionFile）；返第一个匹配。"""
    row = (
        await db.execute(
            select(SessionFile.ephemeral_kb_id)
            .where(
                SessionFile.session_id == session_id,
                SessionFile.deleted_at.is_(None),
                SessionFile.status == "ready",
                SessionFile.ephemeral_kb_id.is_not(None),
            )
            .limit(1)
        )
    ).first()
    return row[0] if row else None


def format_rag_system_prompt(hits: list[dict]) -> str:
    """把检索 hits 拼成 system message 文本（Dify 套路）"""
    lines = [
        "以下是用户在本次会话中上传的文件里检索到的相关内容，请优先参考它们回答用户的问题；",
        "如果信息不足，请明示而非编造。",
        "",
    ]
    for i, h in enumerate(hits, 1):
        src = h.get("filename") or "未命名"
        lines.append(f"[片段 {i} · 来自 {src}]")
        lines.append(str(h.get("snippet") or "").strip())
        lines.append("")
    return "\n".join(lines).strip()


async def search_ephemeral(
    db: AsyncSession,
    *,
    session_id: str,
    query: str,
    top_k: int = 5,
) -> list[dict]:
    """会话级 RAG 检索：若 session 有 ephemeral_kb 且有 ready 的文档，返检索 chunks
    形如 [{filename, source, snippet, score}, ...]；无则返 []。"""
    if not query or not query.strip():
        return []
    kb_id = await resolve_ephemeral_kb_id(db, session_id)
    if not kb_id:
        return []
    from chameleon.core.retrieval.pipeline import RetrievalParams, retrieve

    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        return []
    params = RetrievalParams(
        kb_id=kb.id,
        embedding_model=kb.embedding_model,
        top_k=top_k,
        recall_mode=kb.recall_mode or "hybrid",
    )
    try:
        hits = await retrieve(db, params, query)
    except Exception as e:  # noqa: BLE001
        logger.warning("ephemeral RAG retrieve 失败 session={} err={}", session_id, e)
        return []
    out: list[dict] = []
    for h in hits:
        out.append(
            {
                "filename": h.document_title or "",
                "source": h.document_title or "",
                "snippet": h.content,
                "score": h.score,
            }
        )
    return out


async def cascade_clean_for_session(db: AsyncSession, session_id: str) -> int:
    """session 软删时调：把该 session 所有 SessionFile + 关联 ephemeral_kb 软删。
    返回处理的 file 数量。"""
    files = (
        (
            await db.execute(
                select(SessionFile).where(
                    SessionFile.session_id == session_id,
                    SessionFile.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not files:
        return 0
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    kb_ids = {f.ephemeral_kb_id for f in files if f.ephemeral_kb_id}
    for f in files:
        f.deleted_at = now
        if f.document_id:
            doc = await db.get(Document, f.document_id)
            if doc and doc.deleted_at is None:
                doc.deleted_at = now
        asyncio.create_task(_async_delete_minio(f.object_id))

    # 软删 ephemeral kb 自身
    for kb_id in kb_ids:
        await db.execute(
            update(KnowledgeBase)
            .where(KnowledgeBase.id == kb_id, KnowledgeBase.kind == "ephemeral_session")
            .values(deleted_at=now)
        )
    await db.flush()
    return len(files)
