"""SessionFile service（Phase B v2，已与 KB 解耦）

职责：
1. 记录 session ↔ 文件的关联（SessionFile 行）
2. 解析文档/数据类附件 → 按字符数路由：
   - 小文件（≤ SMALL_FILE_CHAR_THRESHOLD）：parsed_text 存全文，use_full_text=true
   - 大文件：use_full_text=false，切块 + embedding 落到 session_file_chunks（独立向量表）
3. 提供 search_session_files：拼小文件全文 + 大文件向量 top-k，返 hits 给 RAG 注入器
4. 软删 + 级联清理（不再操作 knowledge_bases 域）

设计要点：
- **临时上传不再进知识库**：知识库是用户手动维护的资产，会话临时文件污染那边会让 UI 列表
  又脏又乱。所以 v2 拆出 session_file_chunks 走自己的小型向量检索。
- parsers / chunker / embedding_client 这些「无 KB 状态」的工具复用 KB 域。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.api.response import PageParams, PageResult
from chameleon.core.config import inventory
from chameleon.integrations.embedding.factory import get_embedding_client
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.infra.object_store import get_object_store
from chameleon.data.models import SessionFile, SessionFileChunk
from chameleon.data.utils.snowflake import next_id

# ── 配置 ────────────────────────────────────────────────────

# 小文件阈值：≤ 80K 字符 → 全文直接喂 prompt
# (粗略 ≈ 20K~40K tokens，主流 LLM context 都能放下)
SMALL_FILE_CHAR_THRESHOLD = 80_000

# 大文件切块策略（不暴露给用户配置；走句子级 token 切）
_CHUNK_STRATEGY: dict[str, Any] = {
    "mode": "sentence_token",
    "chunk_size": 400,
    "overlap": 80,
}

# 大文件检索默认 top-k
_DEFAULT_TOP_K = 5

# embedding 批量大小
_EMBED_BATCH = 32


# ── kind 分类（widget 端 classifyKind 的镜像） ─────────


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
        return "other"
    if m in _DATA_MIMES:
        return "data"
    if m.startswith("text/") or m in _DOC_MIMES:
        return "document"
    return "other"


# ── 记账：写 SessionFile + 触发 doc/data 异步解析 ──────────────


async def record_attachments(
    session: AsyncSession,
    *,
    session_id: str,
    end_user_id: str | None,
    attachments: list[dict[str, Any]],
) -> list[SessionFile]:
    """落库 + 触发 document/data 异步解析。返回 SessionFile 行列表。

    finalize 端点和 invoke 都会调本函数；按 (session_id, object_id) 拒绝重复 INSERT。
    """
    if not attachments:
        return []

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
    for att in attachments:
        mime = att.get("mime") or "application/octet-stream"
        kind = classify_kind(mime)
        object_url = att.get("object_url") or ""
        object_id = att.get("object_id") or _extract_object_id_from_url(object_url)
        if object_id and object_id in existing:
            continue
        sf = SessionFile(
            session_id=session_id,
            end_user_id=end_user_id,
            object_url=object_url,
            object_id=object_id,
            filename=att.get("filename") or "unknown",
            mime=mime,
            size=int(att.get("size") or 0),
            kind=kind,
            status="ready" if kind in ("image", "audio") else "parsing",
        )
        session.add(sf)
        rows.append(sf)

    if not rows:
        return []
    await session.flush()

    # 触发 document/data 类型异步解析（不阻塞响应路径）
    for sf in rows:
        if sf.kind in ("document", "data"):
            asyncio.create_task(_async_parse_session_file(sf.id))

    return rows


def _extract_object_id_from_url(url: str) -> str:
    """从 presigned URL 反推 object_id（MinIO path 后段）"""
    try:
        parts = urlparse(url).path.lstrip("/").split("/", 1)
        return parts[1] if len(parts) == 2 else parts[0]
    except Exception:  # noqa: BLE001
        return ""


# ── 异步解析：下载 → parsers.parse → 路由 ─────────────────────


async def _async_parse_session_file(session_file_id: int) -> None:
    """document/data 类型在 record_attachments 之后异步跑。失败置 status='failed'。"""
    async with AsyncSessionLocal() as db:
        sf = await db.get(SessionFile, session_file_id)
        if sf is None:
            return
        try:
            content = _download_object_bytes(sf.object_url, sf.object_id)
            from chameleon.api.knowledge.parsers import parse as parse_doc

            parsed = await parse_doc(content, name=sf.filename, mime_type=sf.mime)
            text = (parsed.text or "").strip()
            sf.text_size = len(text)

            if not text:
                # 解析出空文本 → 标记 failed 让用户感知（不抛业务异常）
                sf.status = "failed"
                sf.error = "文件解析后内容为空（可能是扫描件 / 加密 PDF / 不支持的格式）"
                await db.commit()
                return

            if len(text) <= SMALL_FILE_CHAR_THRESHOLD:
                # 小文件：全文喂 path
                sf.parsed_text = text
                sf.use_full_text = True
                sf.status = "ready"
                await db.commit()
                return

            # 大文件：切块 + embedding
            sf.use_full_text = False
            sf.parsed_text = None
            sf.status = "indexing"
            await db.commit()

            await _chunk_and_embed(db, sf, text)

            sf = await db.get(SessionFile, session_file_id)
            if sf:
                sf.status = "ready"
                await db.commit()
        except Exception as e:  # noqa: BLE001
            logger.exception("session file parse failed sf={}", session_file_id)
            sf = await db.get(SessionFile, session_file_id)
            if sf:
                sf.status = "failed"
                sf.error = str(e)[:500]
                await db.commit()


async def _chunk_and_embed(db: AsyncSession, sf: SessionFile, text: str) -> None:
    """大文件切块 + 批量 embedding + 写 session_file_chunks。"""
    from chameleon.api.knowledge import chunker

    pieces = chunker.split(text, _CHUNK_STRATEGY)
    pieces = [p for p in pieces if p.strip()]
    if not pieces:
        return

    embed_model = inventory.case_embedding()
    if not embed_model:
        raise BusinessError(
            ResultCode.BadRequest,
            message="未配置 embedding 模型（model.json: cases.embedding）",
        )
    embedder = get_embedding_client(embed_model)

    ord_index = 0
    for batch_start in range(0, len(pieces), _EMBED_BATCH):
        batch = pieces[batch_start : batch_start + _EMBED_BATCH]
        vecs = await embedder.embed(batch)
        for content, vec in zip(batch, vecs):
            db.add(
                SessionFileChunk(
                    id=next_id(),
                    session_file_id=sf.id,
                    session_id=sf.session_id,
                    ord_index=ord_index,
                    content=content,
                    embedding=vec,
                    tokens=max(1, len(content) // 2),  # 粗算
                )
            )
            ord_index += 1
        await db.flush()


def _download_object_bytes(object_url: str, object_id: str) -> bytes:
    """优先 MinIO 直读；失败回退 presigned HTTP GET。"""
    store = get_object_store()
    try:
        if object_id:
            return store.get(object_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("MinIO 直读失败，回退 HTTP GET: {}", e)
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
    since: datetime | None = None,
    until: datetime | None = None,
) -> PageResult[SessionFile]:
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
    if since:
        base = base.where(SessionFile.created_at >= since)
    if until:
        base = base.where(SessionFile.created_at <= until)

    from sqlalchemy import func as sa_func

    total = (
        await db.execute(select(sa_func.count()).select_from(base.subquery()))
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
    """软删 SessionFile + 级联清 chunks + MinIO object（异步）"""
    sf = await get_one(db, file_id)
    now = datetime.now(timezone.utc)
    sf.deleted_at = now
    await db.execute(
        update(SessionFileChunk)
        .where(
            SessionFileChunk.session_file_id == sf.id,
            SessionFileChunk.deleted_at.is_(None),
        )
        .values(deleted_at=now)
    )
    await db.flush()
    asyncio.create_task(_async_delete_minio(sf.object_id))


async def _async_delete_minio(object_id: str) -> None:
    if not object_id:
        return
    try:
        store = get_object_store()
        store.delete(object_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("MinIO 删除失败（不影响业务）: {} err={}", object_id, e)


# ── RAG 注入（agent.service / embed.service 调） ────────────────


def format_rag_system_prompt(hits: list[dict]) -> str:
    """把检索 hits 拼成 system message 文本

    区分 full_text（小文件全文）和 chunk（大文件检索片段），分组展示让模型知道哪部分是
    全文哪部分是片段。
    """
    full = [h for h in hits if h.get("mode") == "full_text"]
    chunks = [h for h in hits if h.get("mode") != "full_text"]

    lines: list[str] = []
    if full:
        lines.append("以下是用户在本次会话上传文件的【完整内容】，请基于它们回答用户的问题：")
        lines.append("")
        for h in full:
            src = h.get("filename") or "未命名"
            lines.append(f"=== 文件：{src} ===")
            lines.append(str(h.get("snippet") or "").strip())
            lines.append("")
    if chunks:
        lines.append(
            "以下是用户在本次会话上传的【长文件检索片段】（不是全文），请优先参考它们；"
            "如果信息不足，请明示而非编造："
        )
        lines.append("")
        for i, h in enumerate(chunks, 1):
            src = h.get("filename") or "未命名"
            lines.append(f"[片段 {i} · 来自 {src}]")
            lines.append(str(h.get("snippet") or "").strip())
            lines.append("")
    return "\n".join(lines).strip()


async def search_session_files(
    db: AsyncSession,
    *,
    session_id: str,
    query: str,
    top_k: int = _DEFAULT_TOP_K,
) -> list[dict]:
    """检索 session 所有附件，返 [{filename, snippet, score, mode}, ...]

    - 小文件 use_full_text=true → parsed_text 当一条 full_text hit
    - 大文件 use_full_text=false → 走 session_file_chunks 向量检索 top_k
    """
    if not session_id:
        return []

    hits: list[dict] = []

    # 1. 小文件全文路径（status=ready 且 use_full_text=true）
    full_files = (
        (
            await db.execute(
                select(SessionFile).where(
                    SessionFile.session_id == session_id,
                    SessionFile.deleted_at.is_(None),
                    SessionFile.use_full_text.is_(True),
                    SessionFile.status == "ready",
                    SessionFile.parsed_text.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for f in full_files:
        hits.append(
            {
                "filename": f.filename,
                "snippet": f.parsed_text or "",
                "score": 1.0,
                "mode": "full_text",
            }
        )

    # 2. 大文件向量路径
    if query and query.strip():
        has_chunked = (
            await db.execute(
                select(SessionFile.id)
                .where(
                    SessionFile.session_id == session_id,
                    SessionFile.deleted_at.is_(None),
                    SessionFile.use_full_text.is_(False),
                    SessionFile.status == "ready",
                )
                .limit(1)
            )
        ).first()
        if has_chunked:
            try:
                embed_model = inventory.case_embedding()
                if embed_model:
                    embedder = get_embedding_client(embed_model)
                    qvecs = await embedder.embed([query])
                    qvec = qvecs[0]
                    distance = SessionFileChunk.embedding.cosine_distance(qvec).label("distance")
                    stmt = (
                        select(SessionFileChunk.content, SessionFile.filename, distance)
                        .join(SessionFile, SessionFile.id == SessionFileChunk.session_file_id)
                        .where(
                            SessionFileChunk.session_id == session_id,
                            SessionFileChunk.deleted_at.is_(None),
                            SessionFile.deleted_at.is_(None),
                        )
                        .order_by(distance.asc())
                        .limit(top_k)
                    )
                    rows = (await db.execute(stmt)).all()
                    for content, filename, dist in rows:
                        hits.append(
                            {
                                "filename": filename,
                                "snippet": content,
                                "score": max(0.0, 1.0 - float(dist)),
                                "mode": "chunk",
                            }
                        )
            except Exception as e:  # noqa: BLE001
                logger.warning("session file vector search failed: {}", e)

    return hits


async def cascade_clean_for_session(db: AsyncSession, session_id: str) -> int:
    """session 软删时调：软删 SessionFile + chunks，异步清 MinIO。"""
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
    now = datetime.now(timezone.utc)
    for f in files:
        f.deleted_at = now
        asyncio.create_task(_async_delete_minio(f.object_id))

    await db.execute(
        update(SessionFileChunk)
        .where(
            SessionFileChunk.session_id == session_id,
            SessionFileChunk.deleted_at.is_(None),
        )
        .values(deleted_at=now)
    )
    await db.flush()
    return len(files)
