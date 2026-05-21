"""conversation 模块 HTTP 路由

挂点：/v1/conversations/*
鉴权：require API key（不要求 admin）；普通 key 仅看自己 app_id 的
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.conversation import service
from chameleon.api.conversation.schemas import (
    ConversationItem,
    MessageItem,
)
from chameleon.core.infra.auth import CurrentApp, current_app
from chameleon.core.infra.db import get_session
from chameleon.core.api.response import PageParams, PageResult, Result

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


@router.get("", response_model=Result[PageResult[ConversationItem]])
async def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    agent_key: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[PageResult[ConversationItem]]:
    result = await service.list_conversations(
        session,
        PageParams(page=page, page_size=page_size),
        current_app=app,
        agent_key=agent_key,
    )
    return Result.ok(result)


@router.get("/{session_id}", response_model=Result[ConversationItem])
async def get_conversation(
    session_id: str,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[ConversationItem]:
    item = await service.get_item(session, session_id, current_app=app)
    return Result.ok(item)


@router.get("/{session_id}/messages", response_model=Result[PageResult[MessageItem]])
async def list_messages(
    session_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[PageResult[MessageItem]]:
    result = await service.list_messages(
        session,
        session_id,
        PageParams(page=page, page_size=page_size),
        current_app=app,
    )
    return Result.ok(result)


@router.post("/{session_id}/delete", response_model=Result[ConversationItem])
async def delete_conversation(
    session_id: str,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[ConversationItem]:
    item = await service.soft_delete(session, session_id, current_app=app)
    return Result.ok(item)
