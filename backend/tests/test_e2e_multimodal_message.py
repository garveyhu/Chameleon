"""P19.4 PR #40: 多模态 message 持久化 + history 读回 E2E"""

from __future__ import annotations

import secrets

import pytest_asyncio
from sqlalchemy import delete, select

from chameleon.api.sessions.schemas import AppendMessageDraft
from chameleon.api.sessions.service import append, create, load_messages
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import ChatSession, Message


@pytest_asyncio.fixture
async def mm_session():
    suffix = secrets.token_hex(3)
    app_key = f"e2e-mm-{suffix}"
    async with AsyncSessionLocal() as s:
        conv = await create(
            s, agent_key="example-echo-native", provider="local", app_id=app_key
        )
        sess_id = conv.session_id
        await s.commit()
    yield {"app_key": app_key, "session_id": sess_id}

    async with AsyncSessionLocal() as s:
        await s.execute(delete(Message).where(Message.session_id == sess_id))
        await s.execute(
            delete(ChatSession).where(ChatSession.session_id == sess_id)
        )
        await s.commit()


async def test_append_blocks_persists_and_flattens_content(mm_session: dict):
    sess_id = mm_session["session_id"]
    blocks = [
        {"type": "text", "text": "What is this? "},
        {"type": "image_url", "image_url": {"url": "https://a.com/cat.png"}},
    ]
    async with AsyncSessionLocal() as s:
        m = await append(
            s,
            sess_id,
            AppendMessageDraft(role="user", content="", content_blocks=blocks),
        )
        await s.commit()
        mid = m.id

    async with AsyncSessionLocal() as s:
        row = (
            await s.execute(select(Message).where(Message.id == mid))
        ).scalar_one()
    assert row.content_blocks is not None
    assert len(row.content_blocks) == 2
    assert row.content_blocks[0]["type"] == "text"
    assert row.content_blocks[1]["type"] == "image_url"
    # flatten 同步写到 content（保留老消费者可读）
    assert "What is this?" in row.content
    assert "[image:https://a.com/cat.png]" in row.content


async def test_load_messages_returns_blocks_for_multimodal(mm_session: dict):
    """load_messages 应在 content_blocks 非空时把 content 设为 blocks list"""
    sess_id = mm_session["session_id"]
    async with AsyncSessionLocal() as s:
        await append(
            s,
            sess_id,
            AppendMessageDraft(role="user", content="plain"),
        )
        await append(
            s,
            sess_id,
            AppendMessageDraft(
                role="assistant",
                content="",
                content_blocks=[
                    {"type": "text", "text": "here is "},
                    {"type": "image_url", "image_url": {"url": "https://a.com/y.png", "detail": "high"}},
                ],
            ),
        )
        await s.commit()

    async with AsyncSessionLocal() as s:
        msgs = await load_messages(s, sess_id)

    assert len(msgs) == 2
    # 老消息 content 还是 str
    assert isinstance(msgs[0].content, str)
    assert msgs[0].content == "plain"
    # 多模态消息 content 还原成 list（ProviderMessage 接受 list[ContentBlock]）
    assert isinstance(msgs[1].content, list)
    assert msgs[1].blocks()[0].type == "text"
    assert msgs[1].blocks()[1].type == "image_url"


async def test_legacy_plain_text_path_unchanged(mm_session: dict):
    """老 plain text 写入路径不应触碰 content_blocks 列（保持 NULL）"""
    sess_id = mm_session["session_id"]
    async with AsyncSessionLocal() as s:
        m = await append(
            s,
            sess_id,
            AppendMessageDraft(role="user", content="just text"),
        )
        await s.commit()
        mid = m.id

    async with AsyncSessionLocal() as s:
        row = (
            await s.execute(select(Message).where(Message.id == mid))
        ).scalar_one()
    assert row.content_blocks is None
    assert row.content == "just text"
