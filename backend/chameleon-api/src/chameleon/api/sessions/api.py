"""conversation 模块 HTTP 路由

挂点：/v1/sessions/*
鉴权：api_key OR admin JWT 双轨（current_app_or_admin）——
admin 后台走 JWT 看全量；外部业务方走 api_key 仅看自己 app_id 的
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.sessions import branching, service
from chameleon.api.sessions.schemas import (
    ChatSessionItem,
    MessageItem,
)
from chameleon.core.api.response import PageParams, PageResult, Result
from chameleon.data.infra.auth import CurrentApp, current_app_or_admin
from chameleon.data.infra.db import get_session

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])


@router.get("", response_model=Result[PageResult[ChatSessionItem]])
async def list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    agent_key: str | None = Query(
        None,
        description="agent 过滤 —— app 作用域 key 会自动锁定为 scope_ref（忽略此参数）",
    ),
    user: str | None = Query(
        None, description="按终端用户外部 id 过滤（对应 sessions.end_user_id）"
    ),
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app_or_admin),
) -> Result[PageResult[ChatSessionItem]]:
    result = await service.list_sessions(
        session,
        PageParams(page=page, page_size=page_size),
        current_app=app,
        agent_key=agent_key,
        end_user_id=user,
    )
    return Result.ok(result)


@router.get("/{session_id}", response_model=Result[ChatSessionItem])
async def get_conversation(
    session_id: str,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app_or_admin),
) -> Result[ChatSessionItem]:
    item = await service.get_item(session, session_id, current_app=app)
    return Result.ok(item)


@router.get("/{session_id}/messages", response_model=Result[PageResult[MessageItem]])
async def list_messages(
    session_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app_or_admin),
) -> Result[PageResult[MessageItem]]:
    result = await service.list_messages(
        session,
        session_id,
        PageParams(page=page, page_size=page_size),
        current_app=app,
    )
    return Result.ok(result)


@router.post("/{session_id}/delete", response_model=Result[ChatSessionItem])
async def delete_conversation(
    session_id: str,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app_or_admin),
) -> Result[ChatSessionItem]:
    item = await service.soft_delete(session, session_id, current_app=app)
    return Result.ok(item)


# ── P21.4 分支：regenerate / edit-and-resend ──────────────


class EditAndResendRequest(BaseModel):
    new_content: str = Field(min_length=1, max_length=20_000)


@router.post(
    "/{session_id}/messages/{message_id}/regenerate",
    response_model=Result[MessageItem],
)
async def regenerate_message(
    session_id: str,
    message_id: int,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app_or_admin),
) -> Result[MessageItem]:
    """对某条 assistant 重新生成 → 新 assistant child 挂同 user 父（兄弟分支）

    红线（plan §2 P21）：老 assistant 不删；新 assistant.parent_message_id
    指向同一 user message 形成兄弟分支。
    """
    new_msg = await branching.regenerate_assistant(
        session,
        session_id=session_id,
        message_id=message_id,
        current_app=app,
    )
    return Result.ok(new_msg)


@router.post(
    "/{session_id}/messages/{message_id}/edit-and-resend",
    response_model=Result[MessageItem],
)
async def edit_and_resend(
    session_id: str,
    message_id: int,
    req: EditAndResendRequest,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app_or_admin),
) -> Result[MessageItem]:
    """编辑某 user message → 新 user sibling 分支 + 自动 invoke 新 assistant

    红线：老 user / 老 assistant 不删；新 user.parent_message_id = 老 user 的
    parent → 兄弟分支起点；其后跟新 assistant child。
    """
    new_msg = await branching.edit_and_resend(
        session,
        session_id=session_id,
        message_id=message_id,
        new_content=req.new_content,
        current_app=app,
    )
    return Result.ok(new_msg)
