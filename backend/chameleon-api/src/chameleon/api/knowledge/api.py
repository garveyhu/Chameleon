"""knowledge 对外公开 API（/v1/kbs）

业务方用 api_key 调用。鉴权按密钥作用域（[[api-key-scope-model]]）：
- app 作用域密钥：通吃（可跨 KB 列表 / 创建 / 操作任意 KB）
- kb 作用域密钥（kbs- 前缀）：仅能操作其绑定的 kb_key，跨 KB / 列表 / 创建一律拒绝

admin 后台按 kb_id 走 /v1/admin/kbs/*（另一套）。
"""

import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.knowledge import service
from chameleon.api.knowledge.ingest import run_ingest_task
from chameleon.api.knowledge.schemas import (
    CreateKbRequest,
    DocumentItem,
    IngestQueued,
    IngestRequest,
    KbItem,
    SearchHitItem,
    SearchRequest,
    UpdateDocumentRequest,
    UpdateKbRequest,
)
from chameleon.core.api.exceptions import PermissionDeniedError, ResultCode
from chameleon.core.api.response import PageParams, PageResult, Result
from chameleon.core.infra.auth import CurrentApp, assert_scope, current_app
from chameleon.core.infra.db import get_session

router = APIRouter(prefix="/v1/kbs", tags=["knowledge"])


def _require_app_scope(app: CurrentApp) -> None:
    """跨 KB / 列表 / 创建：仅 app 作用域密钥可用（kb 作用域钥绑定单库，拒绝）。"""
    if app.scope_type != "app":
        raise PermissionDeniedError(
            ResultCode.AgentNotInScope,
            message="该密钥仅限单个知识库，无权列出 / 创建知识库",
        )


@router.get("", response_model=Result[PageResult[KbItem]])
async def list_kbs(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[PageResult[KbItem]]:
    _require_app_scope(app)
    result = await service.list_kbs(session, PageParams(page=page, page_size=page_size))
    return Result.ok(result)


@router.post("", response_model=Result[KbItem])
async def create_kb(
    req: CreateKbRequest,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[KbItem]:
    _require_app_scope(app)
    return Result.ok(await service.create_kb(session, req))


@router.post("/{kb_key}/update", response_model=Result[KbItem])
async def update_kb(
    kb_key: str,
    req: UpdateKbRequest,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[KbItem]:
    assert_scope(app, "kb", kb_key)
    return Result.ok(await service.update_kb(session, kb_key, req))


@router.post("/{kb_key}/delete", response_model=Result[KbItem])
async def delete_kb(
    kb_key: str,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[KbItem]:
    assert_scope(app, "kb", kb_key)
    return Result.ok(await service.delete_kb(session, kb_key))


# ── Documents（增改删查） ─────────────────────────────────


@router.post("/{kb_key}/documents", response_model=Result[IngestQueued])
async def ingest_document(
    kb_key: str,
    req: IngestRequest,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[IngestQueued]:
    assert_scope(app, "kb", kb_key)
    queued, doc, kb = await service.ingest_document(
        session,
        kb_key,
        req,
        app_id=app.app_id,
    )
    # 必须先 commit，否则 asyncio.create_task 的 worker 用独立 session
    # 看不到刚 insert 但未 commit 的 doc/task 行
    await session.commit()

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
    app: CurrentApp = Depends(current_app),
) -> Result[PageResult[DocumentItem]]:
    assert_scope(app, "kb", kb_key)
    return Result.ok(
        await service.list_documents(
            session, kb_key, PageParams(page=page, page_size=page_size)
        )
    )


@router.get(
    "/{kb_key}/documents/{doc_id}", response_model=Result[DocumentItem]
)
async def get_document(
    kb_key: str,
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[DocumentItem]:
    assert_scope(app, "kb", kb_key)
    return Result.ok(await service.get_document(session, kb_key, doc_id))


@router.post(
    "/{kb_key}/documents/{doc_id}/update", response_model=Result[DocumentItem]
)
async def update_document(
    kb_key: str,
    doc_id: int,
    req: UpdateDocumentRequest,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[DocumentItem]:
    assert_scope(app, "kb", kb_key)
    item = await service.update_document(session, kb_key, doc_id, req)
    await session.commit()
    return Result.ok(item)


@router.post(
    "/{kb_key}/documents/{doc_id}/delete",
    response_model=Result[DocumentItem],
)
async def delete_document(
    kb_key: str,
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[DocumentItem]:
    assert_scope(app, "kb", kb_key)
    item = await service.delete_document(session, kb_key, doc_id)
    await session.commit()
    return Result.ok(item)


# ── Search / 检索 ────────────────────────────────────────


@router.post("/{kb_key}/search", response_model=Result[list[SearchHitItem]])
async def search(
    kb_key: str,
    req: SearchRequest,
    app: CurrentApp = Depends(current_app),
) -> Result[list[SearchHitItem]]:
    assert_scope(app, "kb", kb_key)
    return Result.ok(await service.search(kb_key, req))
