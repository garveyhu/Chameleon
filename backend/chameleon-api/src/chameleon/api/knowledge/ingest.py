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

from chameleon.api.knowledge import parsers, storage
from chameleon.api.task import service as task_service
from chameleon.core.config import inventory
from chameleon.core.embedding import get_embedding_client
from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import Document, KnowledgeBase
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
        # 兼容旧字段
        chunk_size = int(doc_chunk_strategy.get("chunk_size") or kb.chunk_size)
        chunk_overlap = int(doc_chunk_strategy.get("overlap") or kb.chunk_overlap)
        source_type = doc.source_type
        source_uri = doc.source_uri
        mime_type = doc.mime_type
        meta = doc.meta or {}
        embedding_model = kb.embedding_model
        doc_title = doc.title

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

    # 4. chunk（v1 fixed；C3.2 切多策略）
    chunks_text = _chunk_fixed(text, chunk_size=chunk_size, overlap=chunk_overlap)
    logger.info(
        "ingest chunked | task={} | doc={} | chunks={}",
        task_id,
        document_id,
        len(chunks_text),
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


def _chunk_fixed(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    """字符级固定切块（v1；C3.2 引入多策略）"""
    if chunk_size <= 0:
        return [text] if text else []
    if overlap < 0 or overlap >= chunk_size:
        overlap = 0
    step = chunk_size - overlap
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        out.append(text[i : i + chunk_size])
        i += step
    return [c for c in out if c.strip()]


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
