"""异步 ingest worker（P16-C 重构）

流水线：
    fetch → parse → chunk → embed → upsert

states: pending → processing → ready / failed

并发：模块级 Semaphore，从 inventory.kb_ingest_concurrency() 读上限。
失败：document.status='failed' + status_message=错误摘要；任务表也同步 failed。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select

from chameleon.api.knowledge import chunker, parsers, storage
from chameleon.api.task import service as task_service
from chameleon.core.config import inventory
from chameleon.core.embedding import ImageEmbedder, get_embedding_client
from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import Chunk, Document, KnowledgeBase
from chameleon.core.vector import ChunkPayload, get_store

# 模块级 semaphore，按 kb_ingest_concurrency() lazy init
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(inventory.kb_ingest_concurrency())
    return _semaphore


async def run_ingest_task(*, task_id: int, document_id: int, kb_id: int) -> None:
    """Background entrypoint（asyncio.create_task 调用）"""
    sem = _get_semaphore()
    async with sem:
        logger.info(
            "ingest worker start | task={} | doc={} | kb={}",
            task_id,
            document_id,
            kb_id,
        )
        try:
            await _execute(task_id=task_id, document_id=document_id, kb_id=kb_id)
        except Exception as e:  # noqa: BLE001
            logger.exception("ingest task failed | task={} | doc={}", task_id, document_id)
            await _mark_failure(
                task_id,
                document_id,
                error={"type": type(e).__name__, "message": str(e)[:500]},
            )


async def _execute(*, task_id: int, document_id: int, kb_id: int) -> None:
    # 1. 进 processing
    async with AsyncSessionLocal() as session:
        await task_service.mark_running(session, task_id)
        await _set_doc_status(session, document_id, "processing")
        await session.commit()

    # 2. 取 kb + doc 快照
    async with AsyncSessionLocal() as session:
        kb = (
            await session.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
            )
        ).scalar_one()
        doc = (
            await session.execute(select(Document).where(Document.id == document_id))
        ).scalar_one()
        kb_chunk_strategy = kb.chunk_strategy or {}
        doc_chunk_strategy = doc.chunk_strategy or kb_chunk_strategy
        # 旧字段兜底（chunk_strategy 不带 chunk_size / overlap 时回到 KB 顶层）
        active_strategy: dict[str, object] = {
            "mode": doc_chunk_strategy.get("mode") or "fixed",
            "chunk_size": int(
                doc_chunk_strategy.get("chunk_size") or kb.chunk_size
            ),
            "overlap": int(
                doc_chunk_strategy.get("overlap") or kb.chunk_overlap
            ),
        }
        if doc_chunk_strategy.get("separator_regex"):
            active_strategy["separator_regex"] = doc_chunk_strategy[
                "separator_regex"
            ]
        # token 模式自动回填 model（embedding_model 或显式传入的 model）
        if active_strategy["mode"] == "token":
            active_strategy["model"] = (
                doc_chunk_strategy.get("model") or kb.embedding_model
            )
        source_type = doc.source_type
        source_uri = doc.source_uri
        mime_type = doc.mime_type
        meta = doc.meta or {}
        embedding_model = kb.embedding_model
        doc_title = doc.title
        doc_kind = doc.kind

    # 2.5 图片文档：走 caption → 文本向量 流程（B5 多模态）
    if doc_kind == "image" or (mime_type or "").startswith("image/"):
        await _ingest_image(
            task_id=task_id,
            document_id=document_id,
            kb_id=kb_id,
            embedding_model=embedding_model,
            source_type=source_type,
            source_uri=source_uri,
            doc_title=doc_title,
        )
        return

    # 3. fetch + parse
    parsed = await _fetch_and_parse(
        source_type=source_type,
        source_uri=source_uri,
        mime_type=mime_type,
        meta=meta,
        name=doc_title,
    )
    text = parsed.text
    if not text or not text.strip():
        raise ValueError("document content is empty after parsing")

    # 4. chunk（按 strategy 分发：fixed / paragraph / sentence / regex）
    chunks_text = chunker.split(text, active_strategy)
    if not chunks_text:
        raise ValueError("chunker produced no chunks")
    logger.info(
        "ingest chunked | task={} | doc={} | chunks={} | mode={}",
        task_id,
        document_id,
        len(chunks_text),
        active_strategy.get("mode"),
    )
    async with AsyncSessionLocal() as session:
        await task_service.mark_progress(
            session, task_id, 30, message=f"chunked into {len(chunks_text)} pieces"
        )
        await session.commit()

    # 5. embed
    embedder = get_embedding_client(embedding_model)
    vectors = await embedder.embed(chunks_text)
    if len(vectors) != len(chunks_text):
        raise RuntimeError(
            f"embedding count mismatch: {len(vectors)} != {len(chunks_text)}"
        )
    async with AsyncSessionLocal() as session:
        await task_service.mark_progress(session, task_id, 70, message="embedded")
        await session.commit()

    # 6. upsert chunks（先清旧 chunks 再写）
    store = get_store()
    await store.delete(kb_id=kb_id, doc_id=document_id)
    payloads = [
        ChunkPayload(
            content=ct,
            embedding=vec,
            seq=i,
            token_count=_approx_tokens(ct),
            meta=None,
        )
        for i, (ct, vec) in enumerate(zip(chunks_text, vectors), start=1)
    ]
    await store.upsert(kb_id=kb_id, doc_id=document_id, chunks=payloads)

    # 7. finalize：写回 doc 统计 + status=ready；merge parsed.metadata 到 doc.meta
    total_tokens = sum(p.token_count or 0 for p in payloads)
    async with AsyncSessionLocal() as session:
        d = (
            await session.execute(select(Document).where(Document.id == document_id))
        ).scalar_one()
        d.status = "ready"
        d.status_message = None
        d.chunk_count = len(payloads)
        d.token_count = total_tokens
        d.meta = {**(d.meta or {}), **{k: v for k, v in parsed.metadata.items() if k != "name"}}
        d.updated_at = datetime.now(timezone.utc)
        await task_service.mark_success(
            session, task_id, result={"chunks": len(payloads), "tokens": total_tokens}
        )
        await session.commit()
    logger.info(
        "ingest done | task={} | doc={} | chunks={} | tokens={}",
        task_id,
        document_id,
        len(payloads),
        total_tokens,
    )


# ── 图片 ingest（B5 多模态） ─────────────────────────────


async def _ingest_image(
    *,
    task_id: int,
    document_id: int,
    kb_id: int,
    embedding_model: str,
    source_type: str,
    source_uri: str | None,
    doc_title: str,
) -> None:
    """图片文档：caption → 文本 embedding → 落 kind='image' chunk（直插 ORM）

    - caption 取图：upload 用临时 presigned URL（供 VLM 抓取），url 类型直接用 URL
    - chunk.source_url 存**稳定引用**：upload 存 object key（读时由 API 层 presign），
      url 类型存原始 URL —— 不存会过期的 presigned URL
    无 VLM（cases.vision 未配）时 ImageEmbedder fallback 文件名 caption，图片仍可检索。
    """
    if not source_uri:
        raise ValueError("image document requires source_uri")
    is_url = source_type == "url"
    # 抓图用 URL（presigned，临时）；存库用稳定引用（object key / 原始 URL）
    fetch_url = source_uri if is_url else storage.presigned_url(source_uri)
    stable_ref = source_uri

    embedder = ImageEmbedder(embedding_model=embedding_model)
    result = await embedder.embed_image(fetch_url, fallback_text=doc_title)
    logger.info(
        "image ingest captioned | task={} | doc={} | source={}",
        task_id,
        document_id,
        result.source,
    )

    # 直插 image chunk（store.upsert 不携带 kind/source_url）；先清旧 chunks
    store = get_store()
    await store.delete(kb_id=kb_id, doc_id=document_id)
    async with AsyncSessionLocal() as session:
        session.add(
            Chunk(
                kb_id=kb_id,
                doc_id=document_id,
                seq=1,
                content=result.caption,
                embedding=result.vector,
                token_count=_approx_tokens(result.caption),
                kind="image",
                source_url=stable_ref,
                meta={"caption_source": result.source},
            )
        )
        d = (
            await session.execute(select(Document).where(Document.id == document_id))
        ).scalar_one()
        d.status = "ready"
        d.status_message = None
        d.kind = "image"
        d.chunk_count = 1
        d.token_count = _approx_tokens(result.caption)
        d.updated_at = datetime.now(timezone.utc)
        await task_service.mark_success(
            session, task_id, result={"chunks": 1, "kind": "image"}
        )
        await session.commit()
    logger.info("image ingest done | task={} | doc={}", task_id, document_id)


# ── helpers ─────────────────────────────────────────────


async def _fetch_and_parse(
    *,
    source_type: str,
    source_uri: str | None,
    mime_type: str | None,
    meta: dict[str, Any],
    name: str,
) -> parsers.ParsedDocument:
    if source_type == "text":
        content = str(meta.get("content") or "")
        return await parsers.parse(content, name=name, mime_type=mime_type or "text/plain")
    if source_type == "url":
        if not source_uri:
            raise ValueError("source_uri required for source_type=url")
        from chameleon.api.knowledge.parsers import url as url_parser
        return await url_parser.fetch_and_parse(source_uri, name=name)
    if source_type == "upload":
        if not source_uri:
            raise ValueError("source_uri required for source_type=upload")
        content_bytes = storage.read_upload(source_uri)
        return await parsers.parse(
            content_bytes, name=name, mime_type=mime_type or "application/octet-stream"
        )
    raise ValueError(f"unsupported source_type: {source_type}")


def _approx_tokens(text: str) -> int:
    """粗估 token：英文 ≈ 4 字符/token，中文 ≈ 1.5 字符/token；取折中"""
    return max(1, len(text) // 3)


async def _set_doc_status(
    session, doc_id: int, status: str, message: str | None = None
) -> None:
    doc = (
        await session.execute(select(Document).where(Document.id == doc_id))
    ).scalar_one()
    doc.status = status
    if message is not None:
        doc.status_message = message
    doc.updated_at = datetime.now(timezone.utc)


async def _mark_failure(
    task_id: int, document_id: int, *, error: dict[str, Any]
) -> None:
    """失败 finalize（独立 session，可能在 session 上下文外被调用）"""
    async with AsyncSessionLocal() as session:
        try:
            await task_service.mark_failed(session, task_id, error)
            await _set_doc_status(
                session,
                document_id,
                "failed",
                message=error.get("message"),
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("ingest failure-finalize itself failed")
