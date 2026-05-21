"""knowledge 模块 HTTP 路由"""

import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.app.modules.knowledge import service
from chameleon.app.modules.knowledge.ingest import run_ingest_task
from chameleon.app.modules.knowledge.schemas import (
    CreateKbRequest,
    DocumentItem,
    IngestQueued,
    IngestRequest,
    KbItem,
    SearchHitItem,
    SearchRequest,
    UpdateKbRequest,
)
from chameleon.core.infra.auth import CurrentApp, current_app
from chameleon.core.infra.db import get_session
from chameleon.core.api.response import PageParams, PageResult, Result

router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])


@router.get("", response_model=Result[PageResult[KbItem]])
async def list_kbs(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _: CurrentApp = Depends(current_app),
) -> Result[PageResult[KbItem]]:
    result = await service.list_kbs(session, PageParams(page=page, page_size=page_size))
    return Result.ok(result)


@router.post("", response_model=Result[KbItem])
async def create_kb(
    req: CreateKbRequest,
    session: AsyncSession = Depends(get_session),
    _: CurrentApp = Depends(current_app),
) -> Result[KbItem]:
    return Result.ok(await service.create_kb(session, req))


@router.post("/{kb_key}/update", response_model=Result[KbItem])
async def update_kb(
    kb_key: str,
    req: UpdateKbRequest,
    session: AsyncSession = Depends(get_session),
    _: CurrentApp = Depends(current_app),
) -> Result[KbItem]:
    return Result.ok(await service.update_kb(session, kb_key, req))


@router.post("/{kb_key}/delete", response_model=Result[KbItem])
async def delete_kb(
    kb_key: str,
    session: AsyncSession = Depends(get_session),
    _: CurrentApp = Depends(current_app),
) -> Result[KbItem]:
    return Result.ok(await service.delete_kb(session, kb_key))


# ── Documents ───────────────────────────────────────────


@router.post("/{kb_key}/documents", response_model=Result[IngestQueued])
async def ingest_document(
    kb_key: str,
    req: IngestRequest,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[IngestQueued]:
    queued, doc, kb = await service.ingest_document(
        session,
        kb_key,
        req,
        app_id=app.app_id,
    )
    # 必须先 commit，否则 asyncio.create_task 的 worker 用独立 session
    # 看不到刚 insert 但未 commit 的 doc/task 行
    await session.commit()

    # 异步 worker（用 asyncio.create_task 而非 BackgroundTasks）
    # 理由：BackgroundTasks 在 httpx ASGITransport 测试下不触发；asyncio 路径在
    # 生产 / 测试行为一致，且 worker 内部已 wrap try/except + logger.exception
    asyncio.create_task(
        run_ingest_task(
            task_id=queued.task_id,
            document_id=doc.id,
            kb_id=kb.id,
        )
    )
    return Result.ok(queued)


@router.get("/{kb_key}/documents", response_model=Result[PageResult[DocumentItem]])
async def list_documents(
    kb_key: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _: CurrentApp = Depends(current_app),
) -> Result[PageResult[DocumentItem]]:
    return Result.ok(
        await service.list_documents(
            session, kb_key, PageParams(page=page, page_size=page_size)
        )
    )


@router.post(
    "/{kb_key}/documents/{doc_id}/delete",
    response_model=Result[DocumentItem],
)
async def delete_document(
    kb_key: str,
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    _: CurrentApp = Depends(current_app),
) -> Result[DocumentItem]:
    return Result.ok(await service.delete_document(session, kb_key, doc_id))


# ── Search ──────────────────────────────────────────────


@router.post("/{kb_key}/search", response_model=Result[list[SearchHitItem]])
async def search(
    kb_key: str,
    req: SearchRequest,
    _: CurrentApp = Depends(current_app),
) -> Result[list[SearchHitItem]]:
    return Result.ok(await service.search(kb_key, req))
