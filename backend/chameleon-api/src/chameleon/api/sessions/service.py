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

from chameleon.api.sessions.schemas import (
    AppendMessageDraft,
    ChatSessionItem,
    MessageItem,
)
from chameleon.core.infra.auth import CurrentApp
from chameleon.core.config import inventory
from chameleon.core.api.exceptions import (
    BusinessError,
    ChatSessionNotFoundError,
    ResultCode,
)
from chameleon.core.models import ChatSession, Message
from chameleon.core.api.response import PageParams, PageResult
from chameleon.core.utils.snowflake import next_session_id
from chameleon.providers.base.types import Message as ProviderMessage

# ── 创建 / 取 / 软删 ──────────────────────────────────────


async def create(
    session: AsyncSession,
    *,
    agent_key: str,
    app_id: str,
    end_user_id: str | None = None,
    api_key_id: int | None = None,
) -> ChatSession:
    """新建会话；session_id 由 chameleon 雪花签发

    S3 重构：新增 end_user_id（终端用户外部标识）+ api_key_id（owner key 反查）。
    """
    sid = next_session_id()
    conv = ChatSession(
        session_id=sid,
        agent_key=agent_key,
        app_id=app_id,
        end_user_id=end_user_id,
        api_key_id=api_key_id,
    )
    session.add(conv)
    await session.flush()
    await session.refresh(conv)
    logger.info(
        "session created | sid={} | agent={} | app={} | user={}",
        sid, agent_key, app_id, end_user_id or "-",
    )
    return conv


async def get(
    session: AsyncSession,
    session_id: str,
    *,
    current_app: CurrentApp | None = None,
) -> ChatSession:
    """取会话；找不到 / 已软删 → ChatSessionNotFoundError

    若传 current_app 且非 admin，会校验 app_id 一致
    """
    stmt = select(ChatSession).where(
        ChatSession.session_id == session_id,
        ChatSession.deleted_at.is_(None),
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise ChatSessionNotFoundError(message=f"session_id 不存在: {session_id}")

    if current_app is not None and "admin" not in current_app.scopes:
        if row.app_id != current_app.app_id:
            # 普通 app 看不到别 app 的会话 → 表现为 NotFound（不泄漏存在性）
            raise ChatSessionNotFoundError(message=f"session_id 不存在: {session_id}")

    return row


async def soft_delete(
    session: AsyncSession,
    session_id: str,
    *,
    current_app: CurrentApp,
) -> ChatSessionItem:
    conv = await get(session, session_id, current_app=current_app)
    conv.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(conv)
    logger.info("conversation soft-deleted | sid={}", session_id)
    return ChatSessionItem.model_validate(conv)


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
    # P19.4 PR #40：content_blocks 非空时 content 取 blocks（多模态消息）；
    # 否则用 plain text content（向后兼容老 history）
    return [
        ProviderMessage(
            role=r.role,
            content=r.content_blocks if r.content_blocks else r.content,
        )
        for r in rows
    ]


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

    # P19.4 PR #40：多模态消息 —— draft.content_blocks 非空时同时写
    # blocks（权威）+ content（flattened 兼容老消费者）
    content_str = draft.content
    blocks = draft.content_blocks
    if blocks:
        from chameleon.providers.base.types import (
            flatten_to_text,
            normalize_content,
        )

        # file_ref 是历史回放专用 block（前端附件 chip），不进 LLM ContentBlock，
        # 也不参与 flatten —— 但要原样落 DB 让历史回放能渲附件
        file_refs = [
            b for b in blocks
            if isinstance(b, dict) and b.get("type") == "file_ref"
        ]
        llm_blocks = [
            b for b in blocks
            if not (isinstance(b, dict) and b.get("type") == "file_ref")
        ]

        if llm_blocks:
            normalized = normalize_content(llm_blocks)
            content_str = flatten_to_text(normalized)
            blocks = [b.model_dump() for b in normalized] + file_refs
        else:
            # 只有 file_ref（少见，正常会有 text block 一起进来）→ content 仍用 draft.content
            blocks = file_refs or None

    msg = Message(
        session_id=session_id,
        seq=next_seq,
        role=draft.role,
        content=content_str,
        content_blocks=blocks,
        steps=draft.steps,
        citations=draft.citations,
        tool_calls=draft.tool_calls,
        usage=draft.usage,
        provider=draft.provider,
        parent_message_id=draft.parent_message_id,
        end_user_id=draft.end_user_id,
        request_id=draft.request_id,
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
            select(ChatSession).where(ChatSession.session_id == session_id)
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


async def list_sessions(
    session: AsyncSession,
    page: PageParams,
    *,
    current_app: CurrentApp,
    agent_key: str | None = None,
    end_user_id: str | None = None,
) -> PageResult[ChatSessionItem]:
    """列会话；scope 解析 Dify 套路：

    - admin（JWT）：全量；可按 agent_key + end_user_id 过滤
    - app 作用域 key（scope_type='app'）：**自动**锁到 scope_ref 对应的 agent，
      调用方无须再传 agent_key；可按 end_user_id 进一步过滤
    - global 作用域 key：限制为本 app_id 标签（来源），可选 agent_key + end_user_id 过滤
    """
    stmt = select(ChatSession).where(ChatSession.deleted_at.is_(None))
    is_admin = "admin" in current_app.scopes

    if not is_admin:
        # 普通 key：限制 app_id 来源标签
        stmt = stmt.where(ChatSession.app_id == current_app.app_id)
        # app 作用域：scope_ref 即目标 agent，自动锁定（覆盖入参）
        if current_app.scope_type == "app" and current_app.scope_ref:
            stmt = stmt.where(ChatSession.agent_key == current_app.scope_ref)
        elif agent_key:
            stmt = stmt.where(ChatSession.agent_key == agent_key)
    elif agent_key:
        stmt = stmt.where(ChatSession.agent_key == agent_key)

    if end_user_id:
        stmt = stmt.where(ChatSession.end_user_id == end_user_id)

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()

    rows = (
        (
            await session.execute(
                stmt.order_by(
                    ChatSession.last_message_at.desc().nullslast(),
                    ChatSession.created_at.desc(),
                )
                .offset(page.offset)
                .limit(page.limit)
            )
        )
        .scalars()
        .all()
    )

    return PageResult(
        items=[ChatSessionItem.model_validate(r) for r in rows],
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
) -> ChatSessionItem:
    conv = await get(session, session_id, current_app=current_app)
    return ChatSessionItem.model_validate(conv)


# ── 兼容性占位（防 BusinessError 兜底报错码漏） ──────────

assert ResultCode.SessionNotFound  # 编译期 sanity check, lint 可移除
# 显式引用 BusinessError 避免 'imported but unused'
_ = BusinessError
