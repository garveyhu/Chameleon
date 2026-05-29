"""对话分支 service —— P21.4 PR #68

regenerate / edit-and-resend：复用现有 provider invoke 路径，新增 assistant /
user message 时填 parent_message_id 形成分支；老消息不删（红线 plan §2 P21）。
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.sessions import service as session_service
from chameleon.api.sessions.schemas import (
    AppendMessageDraft,
    MessageItem,
)
from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.data.infra.auth import CurrentApp
from chameleon.data.models import ChatSession, Message
from chameleon.providers.base import AGENTS, PROVIDERS, InvokeContext
from chameleon.providers.base.types import Message as ProviderMessage


async def regenerate_assistant(
    session: AsyncSession,
    *,
    session_id: str,
    message_id: int,
    current_app: CurrentApp,
) -> MessageItem:
    """对某条 assistant message 重新生成 → 新 assistant child 挂同一 user 父

    红线：老 assistant message 不删；新 assistant.parent_message_id 指向同一
    user message → 形成兄弟分支。
    """
    target, conv = await _load_message_and_conv(
        session, session_id, message_id, current_app
    )
    if target.role != "assistant":
        raise BusinessError(
            ResultCode.ValidationError,
            message="regenerate 仅支持 assistant message",
        )

    # 找该 assistant 的 "源 user message"：取 seq < target.seq 中最近的一条 user
    parent_user = await _find_parent_user(session, session_id, target.seq)
    if parent_user is None:
        raise BusinessError(
            ResultCode.ValidationError,
            message="找不到该 assistant 的源 user message",
        )

    # 拿 agent + provider
    agent_def = AGENTS.get(conv.agent_key)
    if agent_def is None:
        raise BusinessError(
            ResultCode.AgentNotFound,
            message=f"agent 不存在: {conv.agent_key}",
        )
    provider = PROVIDERS.get(agent_def.provider)
    if provider is None:
        raise BusinessError(
            ResultCode.RegistryError,
            message=f"provider 未注册: {agent_def.provider}",
        )

    # 历史：截止到 parent_user 之前的所有 message（不含 target 老 assistant）
    history = await _build_history_up_to(
        session, session_id, parent_user.seq - 1
    )
    user_input = parent_user.content_blocks or parent_user.content

    ctx = InvokeContext(
        agent_def=agent_def,
        input=user_input,
        history=history,
        session_id=session_id,
        provider_conv_id=conv.provider_conv_id,
        context_vars={},
        options={},
        app_id=current_app.app_id,
        stream=False,
        request_id=None,
    )
    result = await provider.invoke(ctx)

    new_msg = await session_service.append(
        session,
        session_id,
        AppendMessageDraft(
            role="assistant",
            content=result.answer,
            steps=[s.model_dump() for s in result.steps] or None,
            citations=[c.model_dump() for c in result.citations] or None,
            tool_calls=[tc.model_dump() for tc in result.tool_calls] or None,
            usage=result.usage.model_dump() if result.usage else None,
            provider=agent_def.provider,
            parent_message_id=parent_user.id,
        ),
    )
    await session_service.touch(session, session_id)
    await session.commit()
    await session.refresh(new_msg)
    logger.info(
        "regenerate done | session={} | old_assistant={} | new_assistant={} | parent_user={}",
        session_id,
        target.id,
        new_msg.id,
        parent_user.id,
    )
    return MessageItem.model_validate(new_msg)


async def edit_and_resend(
    session: AsyncSession,
    *,
    session_id: str,
    message_id: int,
    new_content: str,
    current_app: CurrentApp,
) -> MessageItem:
    """编辑某条 user message → 新 user message 作为同 parent 的 sibling
    分支起点，并自动跑一次 invoke 出新 assistant child

    红线：老 user message 不删；新 user.parent_message_id = 老 user 的 parent
    → 兄弟分支。
    """
    target, conv = await _load_message_and_conv(
        session, session_id, message_id, current_app
    )
    if target.role != "user":
        raise BusinessError(
            ResultCode.ValidationError,
            message="edit-and-resend 仅支持 user message",
        )
    if not new_content or not new_content.strip():
        raise BusinessError(
            ResultCode.ValidationError, message="new_content 不能为空"
        )

    agent_def = AGENTS.get(conv.agent_key)
    if agent_def is None:
        raise BusinessError(
            ResultCode.AgentNotFound,
            message=f"agent 不存在: {conv.agent_key}",
        )
    provider = PROVIDERS.get(agent_def.provider)
    if provider is None:
        raise BusinessError(
            ResultCode.RegistryError,
            message=f"provider 未注册: {agent_def.provider}",
        )

    history = await _build_history_up_to(
        session, session_id, target.seq - 1
    )
    new_user = await session_service.append(
        session,
        session_id,
        AppendMessageDraft(
            role="user",
            content=new_content,
            provider=agent_def.provider,
            parent_message_id=target.parent_message_id,
        ),
    )

    ctx = InvokeContext(
        agent_def=agent_def,
        input=new_content,
        history=history,
        session_id=session_id,
        provider_conv_id=conv.provider_conv_id,
        context_vars={},
        options={},
        app_id=current_app.app_id,
        stream=False,
        request_id=None,
    )
    result = await provider.invoke(ctx)
    new_assistant = await session_service.append(
        session,
        session_id,
        AppendMessageDraft(
            role="assistant",
            content=result.answer,
            steps=[s.model_dump() for s in result.steps] or None,
            citations=[c.model_dump() for c in result.citations] or None,
            tool_calls=[tc.model_dump() for tc in result.tool_calls] or None,
            usage=result.usage.model_dump() if result.usage else None,
            provider=agent_def.provider,
            parent_message_id=new_user.id,
        ),
    )
    await session_service.touch(session, session_id)
    await session.commit()
    await session.refresh(new_assistant)
    logger.info(
        "edit-and-resend done | session={} | old_user={} | new_user={} | new_assistant={}",
        session_id,
        target.id,
        new_user.id,
        new_assistant.id,
    )
    # 返新 assistant（前端切到该分支后会看到新 user + 新 assistant）
    return MessageItem.model_validate(new_assistant)


# ── helpers ────────────────────────────────────────────


async def _load_message_and_conv(
    session: AsyncSession,
    session_id: str,
    message_id: int,
    current_app: CurrentApp,
) -> tuple[Message, ChatSession]:
    """取 message + conversation；校验权属"""
    # 先验权
    conv = await session_service.get(
        session, session_id, current_app=current_app
    )
    msg = (
        await session.execute(
            select(Message).where(
                Message.id == message_id, Message.session_id == session_id
            )
        )
    ).scalar_one_or_none()
    if msg is None:
        raise BusinessError(
            ResultCode.NotFound,
            message=f"message 不存在: id={message_id}",
        )
    return msg, conv


async def _find_parent_user(
    session: AsyncSession, session_id: str, before_seq: int
) -> Message | None:
    """seq < before_seq 中最近的一条 user message"""
    return (
        await session.execute(
            select(Message)
            .where(
                Message.session_id == session_id,
                Message.role == "user",
                Message.seq < before_seq,
            )
            .order_by(Message.seq.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _build_history_up_to(
    session: AsyncSession, session_id: str, max_seq: int
) -> list[ProviderMessage]:
    """构造 ≤ max_seq 的 history（按 seq 正序）"""
    rows = (
        (
            await session.execute(
                select(Message)
                .where(
                    Message.session_id == session_id,
                    Message.seq <= max_seq,
                )
                .order_by(Message.seq.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        ProviderMessage(
            role=r.role,
            content=r.content_blocks if r.content_blocks else r.content,
        )
        for r in rows
    ]


# 显式引用避 lint
_ = datetime, timezone
