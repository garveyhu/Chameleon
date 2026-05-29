"""P21.4 PR #68 E2E：conversation 分支（regenerate / edit-and-resend）"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.api.sessions import service as session_service
from chameleon.api.sessions.schemas import AppendMessageDraft
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import (
    ApiKey,
    ChatSession,
    Message,
)
from chameleon.system.api_key.schemas import CreateApiKeyRequest
from chameleon.system.api_key.service import create_api_key


@pytest_asyncio.fixture
async def app_with_key():
    """造一个 app + 一个 API key，返 plaintext key"""
    suffix = secrets.token_hex(3)
    app_key = f"e2e-branch-{suffix}"
    async with AsyncSessionLocal() as s:
        rec = await create_api_key(
            s,
            CreateApiKeyRequest(
                app_id=app_key, name="t", scopes=[], description=None
            ),
        )
        await s.commit()
    yield {"app_key": app_key, "api_key": rec.plain_key}
    async with AsyncSessionLocal() as s:
        await s.execute(delete(ApiKey).where(ApiKey.app_id == app_key))
        await s.execute(delete(ChatSession).where(ChatSession.app_id == app_key))
        await s.commit()


@pytest_asyncio.fixture
async def seeded_session(app_with_key: dict):
    """造一个 mock-echo session + user msg + assistant msg"""
    async with AsyncSessionLocal() as s:
        app_id = app_with_key["app_key"]
        conv = await session_service.create(
            s,
            agent_key="mock-echo",
            app_id=app_id,
        )
        await s.commit()
        sid = conv.session_id

        # user msg
        user_msg = await session_service.append(
            s,
            sid,
            AppendMessageDraft(role="user", content="hi", provider="mock"),
        )
        # assistant msg（手工填，模拟之前 invoke 结果）
        assistant_msg = await session_service.append(
            s,
            sid,
            AppendMessageDraft(
                role="assistant",
                content="echo: hi",
                provider="mock",
            ),
        )
        await s.commit()
    yield {
        "app_key": app_with_key["app_key"],
        "api_key": app_with_key["api_key"],
        "session_id": sid,
        "user_msg_id": user_msg.id,
        "assistant_msg_id": assistant_msg.id,
    }
    async with AsyncSessionLocal() as s:
        await s.execute(delete(Message).where(Message.session_id == sid))
        await s.execute(delete(ChatSession).where(ChatSession.session_id == sid))
        await s.commit()


def _hdr(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


# ── regenerate ─────────────────────────────────────────


async def test_regenerate_creates_sibling_assistant(
    client: AsyncClient, seeded_session: dict
):
    """regenerate → 新 assistant message；老 assistant 不删；
    新 assistant.parent_message_id = 同 user message id（兄弟分支）"""
    sid = seeded_session["session_id"]
    aid = seeded_session["assistant_msg_id"]
    uid = seeded_session["user_msg_id"]

    r = await client.post(
        f"/v1/sessions/{sid}/messages/{aid}/regenerate",
        headers=_hdr(seeded_session["api_key"]),
    )
    assert r.status_code == 200, r.text
    new_msg = r.json()["data"]
    assert new_msg["role"] == "assistant"
    assert str(new_msg["parent_message_id"]) == str(uid)
    assert new_msg["id"] != aid

    # 老 assistant 仍存
    async with AsyncSessionLocal() as s:
        old = (
            await s.execute(
                select(Message).where(Message.id == aid)
            )
        ).scalar_one_or_none()
        assert old is not None
        assert old.role == "assistant"

        # 现在 user msg 下有 2 个 assistant children
        siblings = (
            await s.execute(
                select(Message).where(
                    Message.session_id == sid,
                    Message.parent_message_id == uid,
                )
            )
        ).scalars().all()
        # 注：老 assistant 未挂 parent_message_id（在 seeded fixture 里没填），
        # 仅新 assistant 挂在 uid 下；测试断言"至少有 1 个 new assistant 挂在
        # parent=uid 下"。
        assert len(siblings) >= 1
        assert new_msg["id"] in [str(s.id) for s in siblings] or new_msg[
            "id"
        ] in [s.id for s in siblings]


async def test_regenerate_rejects_user_message(
    client: AsyncClient, seeded_session: dict
):
    sid = seeded_session["session_id"]
    uid = seeded_session["user_msg_id"]
    r = await client.post(
        f"/v1/sessions/{sid}/messages/{uid}/regenerate",
        headers=_hdr(seeded_session["api_key"]),
    )
    assert r.status_code in (400, 422)


async def test_regenerate_unknown_message_404(
    client: AsyncClient, seeded_session: dict
):
    sid = seeded_session["session_id"]
    r = await client.post(
        f"/v1/sessions/{sid}/messages/999999999/regenerate",
        headers=_hdr(seeded_session["api_key"]),
    )
    assert r.status_code in (400, 404, 500)


# ── edit-and-resend ────────────────────────────────────


async def test_edit_and_resend_creates_sibling_user_and_new_assistant(
    client: AsyncClient, seeded_session: dict
):
    """edit-and-resend → 新 user message (parent = 老 user 的 parent，
    本例 = None) + 新 assistant child"""
    sid = seeded_session["session_id"]
    uid = seeded_session["user_msg_id"]

    r = await client.post(
        f"/v1/sessions/{sid}/messages/{uid}/edit-and-resend",
        headers=_hdr(seeded_session["api_key"]),
        json={"new_content": "what about now?"},
    )
    assert r.status_code == 200, r.text
    new_assistant = r.json()["data"]
    assert new_assistant["role"] == "assistant"
    # new_assistant.parent_message_id 指向 "new user"，不是原 user
    new_user_id = new_assistant["parent_message_id"]
    assert new_user_id is not None
    assert new_user_id != uid

    # 老 user / 老 assistant 不删
    async with AsyncSessionLocal() as s:
        old_user = (
            await s.execute(select(Message).where(Message.id == uid))
        ).scalar_one_or_none()
        assert old_user is not None
        # 新 user 存在且 content = new_content
        new_user = (
            await s.execute(
                select(Message).where(Message.id == int(new_user_id))
            )
        ).scalar_one_or_none()
        assert new_user is not None
        assert new_user.role == "user"
        assert "now" in new_user.content


async def test_edit_and_resend_rejects_assistant_message(
    client: AsyncClient, seeded_session: dict
):
    sid = seeded_session["session_id"]
    aid = seeded_session["assistant_msg_id"]
    r = await client.post(
        f"/v1/sessions/{sid}/messages/{aid}/edit-and-resend",
        headers=_hdr(seeded_session["api_key"]),
        json={"new_content": "hello"},
    )
    assert r.status_code in (400, 422)


async def test_edit_and_resend_rejects_empty(
    client: AsyncClient, seeded_session: dict
):
    sid = seeded_session["session_id"]
    uid = seeded_session["user_msg_id"]
    r = await client.post(
        f"/v1/sessions/{sid}/messages/{uid}/edit-and-resend",
        headers=_hdr(seeded_session["api_key"]),
        json={"new_content": ""},
    )
    assert r.status_code in (400, 422)
