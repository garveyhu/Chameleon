"""异步 ingest worker

v1：FastAPI BackgroundTasks。流程：
  task.running → 取 doc → 切块 → 批量 embed → upsert chunks → doc.ready / task.success

失败：doc.failed + task.failed（error JSONB 含 type/message）

切块策略 v1：纯字符切（chunk_size + overlap）。未来切 tokenizer-aware。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger
from sqlalchemy import select

from chameleon.app.modules.task import service as task_service
from chameleon.core.db import AsyncSessionLocal
from chameleon.core.embedding import get_embedding_client
from chameleon.core.models import Document, KnowledgeBase
from chameleon.core.vector import ChunkPayload, get_store

_HTTP_TIMEOUT = 30.0


async def run_ingest_task(*, task_id: int, document_id: int, kb_id: int) -> None:
    """Background entrypoint（被 BackgroundTasks 调）"""
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
            error={
                "type": type(e).__name__,
                "message": str(e)[:500],
            },
        )


async def _execute(*, task_id: int, document_id: int, kb_id: int) -> None:
    # task → running
    async with AsyncSessionLocal() as session:
        await task_service.mark_running(session, task_id)
        await _set_doc_status(session, document_id, "chunking")
        await session.commit()

    # 取 kb + doc
    async with AsyncSessionLocal() as session:
        kb = (
            await session.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
            )
        ).scalar_one()
        doc = (
            await session.execute(select(Document).where(Document.id == document_id))
        ).scalar_one()
        chunk_size = kb.chunk_size
        chunk_overlap = kb.chunk_overlap
        source_type = doc.source_type
        source_uri = doc.source_uri
        meta = doc.meta or {}
        embedding_model = kb.embedding_model

    # 抓内容
    raw_text = await _fetch_content(source_type, source_uri, meta)
    if not raw_text or not raw_text.strip():
        raise ValueError("document content is empty")

    # 切块
    chunks_text = _chunk(raw_text, chunk_size=chunk_size, overlap=chunk_overlap)
    logger.info(
        "ingest chunking done | task={} | doc={} | chunks={}",
        task_id,
        document_id,
        len(chunks_text),
    )

    async with AsyncSessionLocal() as session:
        await task_service.mark_progress(
            session, task_id, 30, message=f"chunked into {len(chunks_text)} pieces"
        )
        await _set_doc_status(session, document_id, "embedding")
        await session.commit()

    # 批量 embed
    embedder = get_embedding_client(embedding_model)
    vectors = await embedder.embed(chunks_text)
    if len(vectors) != len(chunks_text):
        raise RuntimeError(
            f"embedding count mismatch: {len(vectors)} != {len(chunks_text)}"
        )

    async with AsyncSessionLocal() as session:
        await task_service.mark_progress(session, task_id, 70, message="embedded")
        await session.commit()

    # upsert chunks
    store = get_store()
    payloads = [
        ChunkPayload(
            content=chunk,
            embedding=vec,
            seq=i,
            token_count=_approx_tokens(chunk),
            meta=None,
        )
        for i, (chunk, vec) in enumerate(zip(chunks_text, vectors), start=1)
    ]
    await store.upsert(kb_id=kb_id, doc_id=document_id, chunks=payloads)

    # finalize
    async with AsyncSessionLocal() as session:
        await _set_doc_status(session, document_id, "ready")
        await task_service.mark_success(
            session,
            task_id,
            result={"chunks": len(payloads)},
        )
        await session.commit()
    logger.info(
        "ingest worker done | task={} | doc={} | chunks={}",
        task_id,
        document_id,
        len(payloads),
    )


# ── helpers ─────────────────────────────────────────────


async def _fetch_content(
    source_type: str, source_uri: str | None, meta: dict[str, Any]
) -> str:
    if source_type == "text":
        return str(meta.get("content") or "")
    if source_type == "url":
        if not source_uri:
            raise ValueError("source_uri required for source_type=url")
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(source_uri)
            resp.raise_for_status()
            return resp.text
    raise ValueError(f"unsupported source_type: {source_type}")


def _chunk(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    """简单字符切块（v1）"""
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
