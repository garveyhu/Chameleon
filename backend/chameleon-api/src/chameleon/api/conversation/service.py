"""conversation 业务服务

核心职责：
- create / get / load_messages / append / touch / soft_delete
- 跨模块调用入口（被 agent 模块的 service 使用）
- 普通 app key 只能访问 app_id 匹配的 conversations；admin scope 可看全量
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.conversation.schemas import (
    AppendMessageDraft,
    ConversationItem,
    MessageItem,
)
from chameleon.core.infra.auth import CurrentApp
from chameleon.core.config import inventory
from chameleon.core.api.exceptions import (
    BusinessError,
    ConversationNotFoundError,
    ResultCode,
)
from chameleon.core.models import Conversation, Message
from chameleon.core.api.response import PageParams, PageResult
from chameleon.core.utils.snowflake import next_session_id
from chameleon.providers.base.types import Message as ProviderMessage

# ── 创建 / 取 / 软删 ──────────────────────────────────────


async def create(
    session: AsyncSession,
    *,
    agent_key: str,
    provider: str,
    app_id: str,
) -> Conversation:
    """新建会话；session_id 由 chameleon 雪花签发"""
    sid = next_session_id()
    conv = Conversation(
        session_id=sid,
        agent_key=agent_key,
        provider=provider,
        app_id=app_id,
    )
    session.add(conv)
    await session.flush()
    await session.refresh(conv)
    logger.info(
        "conversation created | sid={} | agent={} | app={}", sid, agent_key, app_id
    )
    return conv


async def get(
    session: AsyncSession,
    session_id: str,
    *,
    current_app: CurrentApp | None = None,
) -> Conversation:
    """取会话；找不到 / 已软删 → ConversationNotFoundError

    若传 current_app 且非 admin，会校验 app_id 一致
    """
    stmt = select(Conversation).where(
        Conversation.session_id == session_id,
        Conversation.deleted_at.is_(None),
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise ConversationNotFoundError(message=f"session_id 不存在: {session_id}")

    if current_app is not None and "admin" not in current_app.scopes:
        if row.app_id != current_app.app_id:
            # 普通 app 看不到别 app 的会话 → 表现为 NotFound（不泄漏存在性）
            raise ConversationNotFoundError(message=f"session_id 不存在: {session_id}")

    return row


async def soft_delete(
    session: AsyncSession,
    session_id: str,
    *,
    current_app: CurrentApp,
) -> ConversationItem:
    conv = await get(session, session_id, current_app=current_app)
    conv.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(conv)
    logger.info("conversation soft-deleted | sid={}", session_id)
    return ConversationItem.model_validate(conv)


# ── 历史装载 / 追加 ─────────────────────────────────────


async def load_messages(
    session: AsyncSession,
    session_id: str,
    *,
    limit: int | None = None,
) -> list[ProviderMessage]:
    """取最新 limit 条历史，按 seq 正序返回（用于 InvokeContext.history）

    返回的是 ProviderMessage（providers-base 的 Message 类型），不是 ORM。
    """
    if limit is None:
        limit = inventory.session_history_limit()

    # 取最新 N 条（seq desc，limit），再正序返回
    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.seq.desc())
        .limit(limit)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    rows.reverse()  # 时间正序
    return [ProviderMessage(role=r.role, content=r.content) for r in rows]


async def append(
    session: AsyncSession,
    session_id: str,
    draft: AppendMessageDraft,
) -> Message:
    """追加一条消息，seq 自动 +1（取当前 MAX seq + 1）"""
    next_seq = (
        await session.execute(
            select(func.coalesce(func.max(Message.seq), 0) + 1).where(
                Message.session_id == session_id
            )
        )
    ).scalar_one()

    msg = Message(
        session_id=session_id,
        seq=next_seq,
        role=draft.role,
        content=draft.content,
        steps=draft.steps,
        citations=draft.citations,
        tool_calls=draft.tool_calls,
        usage=draft.usage,
        provider=draft.provider,
        created_at=datetime.now(timezone.utc),
    )
    session.add(msg)
    await session.flush()
    return msg


# ── touch（更新 last_message_at / title / provider_conv_id） ──


async def touch(
    session: AsyncSession,
    session_id: str,
    *,
    title: str | None = None,
    provider_conv_id: str | None = None,
) -> None:
    """更新会话状态字段（不抛 NotFound，找不到就跳过）"""
    conv = (
        await session.execute(
            select(Conversation).where(Conversation.session_id == session_id)
        )
    ).scalar_one_or_none()
    if conv is None:
        return

    conv.last_message_at = datetime.now(timezone.utc)
    if title is not None and conv.title is None:
        conv.title = title[: inventory.session_title_max_length()]
    if provider_conv_id is not None and conv.provider_conv_id is None:
        conv.provider_conv_id = provider_conv_id
    await session.flush()


# ── 列表查询 ────────────────────────────────────────────


async def list_conversations(
    session: AsyncSession,
    page: PageParams,
    *,
    current_app: CurrentApp,
    agent_key: str | None = None,
) -> PageResult[ConversationItem]:
    stmt = select(Conversation).where(Conversation.deleted_at.is_(None))

    # 普通 app 仅看自己的；admin 看全量
    if "admin" not in current_app.scopes:
        stmt = stmt.where(Conversation.app_id == current_app.app_id)

    if agent_key:
        stmt = stmt.where(Conversation.agent_key == agent_key)

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()

    rows = (
        (
            await session.execute(
                stmt.order_by(
                    Conversation.last_message_at.desc().nullslast(),
                    Conversation.created_at.desc(),
                )
                .offset(page.offset)
                .limit(page.limit)
            )
        )
        .scalars()
        .all()
    )

    return PageResult(
        items=[ConversationItem.model_validate(r) for r in rows],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


async def list_messages(
    session: AsyncSession,
    session_id: str,
    page: PageParams,
    *,
    current_app: CurrentApp,
) -> PageResult[MessageItem]:
    # 先验权
    await get(session, session_id, current_app=current_app)

    stmt = select(Message).where(Message.session_id == session_id)
    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()

    rows = (
        (
            await session.execute(
                stmt.order_by(Message.seq.asc()).offset(page.offset).limit(page.limit)
            )
        )
        .scalars()
        .all()
    )

    return PageResult(
        items=[MessageItem.model_validate(r) for r in rows],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


async def get_item(
    session: AsyncSession,
    session_id: str,
    *,
    current_app: CurrentApp,
) -> ConversationItem:
    conv = await get(session, session_id, current_app=current_app)
    return ConversationItem.model_validate(conv)


# ── 兼容性占位（防 BusinessError 兜底报错码漏） ──────────

assert ResultCode.ConversationNotFound  # 编译期 sanity check, lint 可移除
# 显式引用 BusinessError 避免 'imported but unused'
_ = BusinessError
