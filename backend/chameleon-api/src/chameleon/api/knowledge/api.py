"""knowledge 对外公开 API（/v1/kb）—— Dify 风扁平契约

**key 即知识库身份**——`Authorization: Bearer kbs-xxx` 已经唯一标识了这条 key 绑定的 KB，
路径中**不再带** `kb_key` 占位。同一套路对齐 agent 的 `/v1/invoke` + `/v1/info`。

鉴权按密钥作用域（[[api-key-scope-model]]）：
- `kb` 作用域密钥（kbs- 前缀）：仅能操作 scope_ref 指向的那一个 KB
- `global` 作用域密钥：可在 body / query 显式带 `kb_key` 指定目标 KB
- `app` 作用域密钥：不支持 KB 操作

KB 列表 / 创建 → 走 `/v1/admin/kbs/*`（JWT 鉴权的管理路径），公开 API 不再暴露。
"""

import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.knowledge import service
from chameleon.api.knowledge.ingest import run_ingest_task
from chameleon.api.knowledge.schemas import (
    DocumentItem,
    IngestQueued,
    IngestRequest,
    KbItem,
    SearchHitItem,
    SearchRequest,
    UpdateDocumentRequest,
    UpdateKbRequest,
)
from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.api.response import PageParams, PageResult, Result
from chameleon.data.infra.auth import CurrentApp, current_app
from chameleon.data.infra.db import get_session

router = APIRouter(prefix="/v1/kb", tags=["knowledge"])


def _resolve_kb_key_from_key(app: CurrentApp, body_kb_key: str | None) -> str:
    """从 key scope + body/query 解析目标 kb_key（Dify 套路：key 已隐含 KB 身份）

    - scope_type='kb'：必须用 scope_ref（key 绑定的 KB）；body 若传需匹配
    - scope_type='global'：body / query 必须带 kb_key
    - scope_type='app' 等：禁止操作 KB
    """
    if app.scope_type == "kb":
        target = app.scope_ref or ""
        if not target:
            raise BusinessError(
                ResultCode.ValidationError, message="kb 作用域 key 缺 scope_ref"
            )
        if body_kb_key and body_kb_key != target:
            raise BusinessError(
                ResultCode.ValidationError,
                message=f"该密钥仅绑定 {target}，不可操作 {body_kb_key}",
            )
        return target
    if app.scope_type == "global":
        if not body_kb_key:
            raise BusinessError(
                ResultCode.ValidationError,
                message="全局 key 需在 body / query 指定 kb_key",
            )
        return body_kb_key
    raise BusinessError(
        ResultCode.ValidationError,
        message=f"该 key 不支持 KB 操作（scope_type={app.scope_type}）",
    )


# ── KB 元信息（GET /v1/kb 等价 agent 的 /v1/info）─────────────


@router.get("", response_model=Result[KbItem])
async def get_kb_info(
    kb_key: str | None = Query(None, description="仅 global 作用域 key 需要"),
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[KbItem]:
    """返当前 key 绑定的 KB 元信息（kb_key / name / description / 等）"""
    target_kb_key = _resolve_kb_key_from_key(app, kb_key)
    return Result.ok(await service.get_kb(session, target_kb_key))


@router.post("/update", response_model=Result[KbItem])
async def update_kb(
    req: UpdateKbRequest,
    kb_key: str | None = Query(None, description="仅 global 作用域 key 需要"),
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[KbItem]:
    target_kb_key = _resolve_kb_key_from_key(app, kb_key)
    return Result.ok(await service.update_kb(session, target_kb_key, req))


@router.post("/delete", response_model=Result[KbItem])
async def delete_kb(
    kb_key: str | None = Query(None, description="仅 global 作用域 key 需要"),
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[KbItem]:
    target_kb_key = _resolve_kb_key_from_key(app, kb_key)
    return Result.ok(await service.delete_kb(session, target_kb_key))


# ── Documents（增改删查） ─────────────────────────────────


@router.post("/documents", response_model=Result[IngestQueued])
async def ingest_document(
    req: IngestRequest,
    kb_key: str | None = Query(None, description="仅 global 作用域 key 需要"),
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[IngestQueued]:
    target_kb_key = _resolve_kb_key_from_key(app, kb_key)
    queued, doc, kb = await service.ingest_document(
        session,
        target_kb_key,
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


@router.get("/documents", response_model=Result[PageResult[DocumentItem]])
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    kb_key: str | None = Query(None, description="仅 global 作用域 key 需要"),
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[PageResult[DocumentItem]]:
    target_kb_key = _resolve_kb_key_from_key(app, kb_key)
    return Result.ok(
        await service.list_documents(
            session, target_kb_key, PageParams(page=page, page_size=page_size)
        )
    )


@router.get("/documents/{doc_id}", response_model=Result[DocumentItem])
async def get_document(
    doc_id: int,
    kb_key: str | None = Query(None, description="仅 global 作用域 key 需要"),
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[DocumentItem]:
    target_kb_key = _resolve_kb_key_from_key(app, kb_key)
    return Result.ok(await service.get_document(session, target_kb_key, doc_id))


@router.post("/documents/{doc_id}/update", response_model=Result[DocumentItem])
async def update_document(
    doc_id: int,
    req: UpdateDocumentRequest,
    kb_key: str | None = Query(None, description="仅 global 作用域 key 需要"),
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[DocumentItem]:
    target_kb_key = _resolve_kb_key_from_key(app, kb_key)
    item = await service.update_document(session, target_kb_key, doc_id, req)
    await session.commit()
    return Result.ok(item)


@router.post("/documents/{doc_id}/delete", response_model=Result[DocumentItem])
async def delete_document(
    doc_id: int,
    kb_key: str | None = Query(None, description="仅 global 作用域 key 需要"),
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[DocumentItem]:
    target_kb_key = _resolve_kb_key_from_key(app, kb_key)
    item = await service.delete_document(session, target_kb_key, doc_id)
    await session.commit()
    return Result.ok(item)


# ── Search / 检索 ────────────────────────────────────────


@router.post("/search", response_model=Result[list[SearchHitItem]])
async def search(
    req: SearchRequest,
    kb_key: str | None = Query(None, description="仅 global 作用域 key 需要"),
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[list[SearchHitItem]]:
    target_kb_key = _resolve_kb_key_from_key(app, kb_key)
    return Result.ok(await service.search(session, target_kb_key, req))
