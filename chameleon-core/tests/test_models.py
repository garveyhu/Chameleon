"""共享 ORM 模型基本 round-trip 测试

不开启事务回滚 fixture——每个测试自己清理（v1 简版）。
"""

import secrets
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select

from chameleon.core.db import AsyncSessionLocal
from chameleon.core.models import ApiKey, Conversation, Message
from chameleon.core.utils.snowflake import next_id


@pytest.fixture(autouse=True)
async def _cleanup_after_test():
    yield
    # 测试后清理（按外键依赖倒序）
    async with AsyncSessionLocal() as s:
        await s.execute(delete(Message))
        await s.execute(delete(Conversation))
        await s.execute(delete(ApiKey).where(ApiKey.app_id.like("test-%")))
        await s.commit()


async def test_create_api_key_roundtrip() -> None:
    rand = secrets.token_hex(4)
    async with AsyncSessionLocal() as s:
        key = ApiKey(
            app_id=f"test-{rand}",
            name="t",
            key_hash="h" * 64,
            key_prefix="chm_test",
            scopes=["admin"],
            description="test admin key",
        )
        s.add(key)
        await s.commit()
        await s.refresh(key)
        assert key.id > 0
        assert key.created_at is not None
        assert key.scopes == ["admin"]


async def test_conversation_with_messages() -> None:
    rand = secrets.token_hex(4)
    sid = f"sess_{rand}"
    async with AsyncSessionLocal() as s:
        conv = Conversation(
            session_id=sid,
            agent_key="echo",
            provider="langgraph",
            app_id=f"test-{rand}",
        )
        s.add(conv)
        await s.flush()

        s.add_all(
            [
                Message(
                    session_id=sid,
                    seq=1,
                    role="user",
                    content="hi",
                    created_at=datetime.now(timezone.utc),
                ),
                Message(
                    session_id=sid,
                    seq=2,
                    role="assistant",
                    content="hello",
                    created_at=datetime.now(timezone.utc),
                ),
            ]
        )
        await s.commit()

        rows = (
            (
                await s.execute(
                    select(Message)
                    .where(Message.session_id == sid)
                    .order_by(Message.seq)
                )
            )
            .scalars()
            .all()
        )
        assert [m.role for m in rows] == ["user", "assistant"]
        assert [m.content for m in rows] == ["hi", "hello"]


async def test_snowflake_id_unique_and_increasing() -> None:
    ids = [next_id() for _ in range(100)]
    assert len(set(ids)) == 100, "duplicates produced"
    assert ids == sorted(ids), "ids not monotonically increasing"
