"""P18.5 PR #27: message.parent_message_id 持久化 + 列接口透出"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

import pytest_asyncio
from sqlalchemy import delete, select

from chameleon.api.conversation.schemas import AppendMessageDraft
from chameleon.api.conversation.service import append, create
from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import App, Conversation, Message


@pytest_asyncio.fixture
async def smoke_session():
    suffix = secrets.token_hex(3)
    app_key = f"e2e-br-{suffix}"
    async with AsyncSessionLocal() as s:
        s.add(App(app_key=app_key, name="branch test", status="active"))
        await s.flush()
        conv = await create(
            s, agent_key="example", provider="local", app_id=app_key
        )
        sess_id = conv.session_id
        await s.commit()
    yield {"app_key": app_key, "session_id": sess_id}

    async with AsyncSessionLocal() as s:
        await s.execute(delete(Message).where(Message.session_id == sess_id))
        await s.execute(
            delete(Conversation).where(Conversation.session_id == sess_id)
        )
        await s.execute(delete(App).where(App.app_key == app_key))
        await s.commit()


async def test_append_message_stores_parent_message_id(smoke_session: dict):
    """append AppendMessageDraft 带 parent_message_id 时持久化"""
    session_id = smoke_session["session_id"]

    async with AsyncSessionLocal() as s:
        m1 = await append(
            s,
            session_id,
            AppendMessageDraft(role="user", content="原始问题"),
        )
        m2 = await append(
            s,
            session_id,
            AppendMessageDraft(role="assistant", content="原始回答"),
        )
        # regenerate：再来一条 assistant，parent_message_id 指向 m1（fork 起点 = user）
        m3 = await append(
            s,
            session_id,
            AppendMessageDraft(
                role="assistant",
                content="重新生成的回答",
                parent_message_id=m1.id,
            ),
        )
        await s.commit()

    async with AsyncSessionLocal() as s:
        rows = (
            (
                await s.execute(
                    select(Message)
                    .where(Message.session_id == session_id)
                    .order_by(Message.seq.asc())
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 3
    assert rows[0].parent_message_id is None  # user 主线
    assert rows[1].parent_message_id is None  # assistant 主线
    assert rows[2].parent_message_id == rows[0].id  # 分支：fork from user
    # 验证排序
    assert [r.seq for r in rows] == [1, 2, 3]


async def test_message_item_schema_exposes_parent_id(smoke_session: dict):
    """MessageItem schema 包含 parent_message_id 字段"""
    from chameleon.api.conversation.schemas import MessageItem

    session_id = smoke_session["session_id"]
    async with AsyncSessionLocal() as s:
        m = await append(
            s,
            session_id,
            AppendMessageDraft(
                role="user",
                content="x",
                parent_message_id=12345,
            ),
        )
        await s.commit()
        item = MessageItem.model_validate(m)
        assert item.parent_message_id == 12345


async def test_message_branch_tree_query(smoke_session: dict):
    """按 parent_message_id 索引能反查 children"""
    session_id = smoke_session["session_id"]

    async with AsyncSessionLocal() as s:
        m_root = await append(
            s, session_id, AppendMessageDraft(role="user", content="root")
        )
        # 两个分支都 fork from m_root
        await append(
            s,
            session_id,
            AppendMessageDraft(
                role="assistant",
                content="branch A",
                parent_message_id=m_root.id,
            ),
        )
        await append(
            s,
            session_id,
            AppendMessageDraft(
                role="assistant",
                content="branch B",
                parent_message_id=m_root.id,
            ),
        )
        await s.commit()

    async with AsyncSessionLocal() as s:
        children = (
            (
                await s.execute(
                    select(Message).where(
                        Message.parent_message_id == m_root.id
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(children) == 2
    contents = {c.content for c in children}
    assert contents == {"branch A", "branch B"}
