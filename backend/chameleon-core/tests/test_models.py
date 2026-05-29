"""共享 ORM 模型基本 round-trip 测试

单租户重构后：app_id 是自由「来源标签」字符串（无 FK→apps），agent_key 为字符串。
"""

import secrets
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import (
    Agent,
    ApiKey,
    ChatSession,
    LLMModel,
    Message,
    Permission,
    Provider,
    Role,
    RolePermission,
    User,
    UserRole,
)
from chameleon.data.utils.snowflake import next_id


@pytest.fixture(autouse=True)
async def _cleanup_after_test():
    yield
    async with AsyncSessionLocal() as s:
        # 按 FK 依赖倒序清
        await s.execute(delete(Message))
        await s.execute(delete(ChatSession).where(ChatSession.app_id.like("test-%")))
        await s.execute(delete(ApiKey).where(ApiKey.app_id.like("test-%")))
        await s.execute(delete(Agent).where(Agent.agent_key.like("test-%")))
        await s.execute(delete(LLMModel).where(LLMModel.code.like("test-%")))
        await s.execute(delete(Provider).where(Provider.code.like("test-%")))
        await s.execute(delete(User).where(User.username.like("test-%")))
        await s.execute(delete(Role).where(Role.code.like("test-%")))
        await s.execute(delete(Permission).where(Permission.code.like("test-%")))
        await s.commit()


# ── v0.1 兼容（按新 FK schema 重写） ───────────────────────


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
        assert key.scopes == ["admin"]


async def test_conversation_with_messages() -> None:
    rand = secrets.token_hex(4)
    sid = f"sess_{rand}"
    async with AsyncSessionLocal() as s:
        agent = Agent(
            agent_key=f"test-agent-{rand}",
            name="test agent",
            source="local",
            local_class_path="x.Y",
        )
        s.add(agent)
        await s.flush()

        conv = ChatSession(
            session_id=sid,
            agent_key=f"test-agent-{rand}",
            app_id=f"test-{rand}",
        )
        s.add(conv)
        await s.flush()

        s.add_all(
            [
                Message(session_id=sid, seq=1, role="user", content="hi",
                        created_at=datetime.now(timezone.utc)),
                Message(session_id=sid, seq=2, role="assistant", content="hello",
                        created_at=datetime.now(timezone.utc)),
            ]
        )
        await s.commit()

        rows = (
            (await s.execute(
                select(Message).where(Message.session_id == sid).order_by(Message.seq)
            )).scalars().all()
        )
        assert [m.role for m in rows] == ["user", "assistant"]


async def test_snowflake_id_unique_and_increasing() -> None:
    ids = [next_id() for _ in range(100)]
    assert len(set(ids)) == 100
    assert ids == sorted(ids)


# ── 新表：鉴权域 ────────────────────────────────────────


async def test_user_role_permission_chain() -> None:
    rand = secrets.token_hex(4)
    async with AsyncSessionLocal() as s:
        perm_r = Permission(code=f"test-r-{rand}", resource="t", action="read")
        perm_w = Permission(code=f"test-w-{rand}", resource="t", action="write")
        role = Role(code=f"test-{rand}", name="test role")
        user = User(
            username=f"test-{rand}",
            password_hash="$argon2id$fake",
        )
        s.add_all([perm_r, perm_w, role, user])
        await s.flush()

        # 用关联表对象 add（避免 ORM 关系赋值在 async 下的 greenlet 坑）
        s.add_all(
            [
                RolePermission(role_id=role.id, permission_id=perm_r.id),
                RolePermission(role_id=role.id, permission_id=perm_w.id),
                UserRole(user_id=user.id, role_id=role.id),
            ]
        )
        await s.commit()

        # 读：显式 eager load 跨 commit 边界
        loaded = (
            await s.execute(
                select(User)
                .where(User.username == f"test-{rand}")
                .options(selectinload(User.roles).selectinload(Role.permissions))
            )
        ).scalar_one()
        assert len(loaded.roles) == 1
        assert {p.code for p in loaded.roles[0].permissions} == {
            f"test-r-{rand}",
            f"test-w-{rand}",
        }


async def test_user_username_unique() -> None:
    rand = secrets.token_hex(4)
    name = f"test-{rand}"
    async with AsyncSessionLocal() as s:
        s.add(User(username=name, password_hash="x"))
        await s.commit()

        s.add(User(username=name, password_hash="y"))
        with pytest.raises(Exception):
            await s.commit()
        await s.rollback()


# ── 新表：模型 / agent 域 ──────────────────────────────


async def test_provider_model_agent_chain() -> None:
    rand = secrets.token_hex(4)
    async with AsyncSessionLocal() as s:
        prov = Provider(code=f"test-{rand}", kind="llm", name="t-llm")
        s.add(prov)
        await s.flush()

        model = LLMModel(provider_id=prov.id, code=f"test-{rand}-m", kind="chat")
        s.add(model)
        await s.flush()

        agent = Agent(
            agent_key=f"test-agent-{rand}",
            name="t",
            source="local",
            local_class_path="x.Y",
            provider_id=prov.id,
            default_model_code=model.code,
        )
        s.add(agent)
        await s.commit()
        await s.refresh(agent)
        assert agent.provider_id == prov.id
        assert agent.default_model_code == model.code


async def test_agent_key_unique() -> None:
    rand = secrets.token_hex(4)
    name = f"test-agent-{rand}"
    async with AsyncSessionLocal() as s:
        s.add(Agent(agent_key=name, name="t", source="local", local_class_path="x.Y"))
        await s.commit()

        s.add(Agent(agent_key=name, name="t2", source="local", local_class_path="x.Y2"))
        with pytest.raises(Exception):
            await s.commit()
        await s.rollback()
