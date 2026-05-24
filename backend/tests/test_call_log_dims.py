"""P23.C1: call_logs 计费多维列 user_id / model_code / channel_id

覆盖：
- record_call 落库三列（user / model / channel）
- 不传时三列为 NULL（老数据零迁移升级）
- channel 删除后 channel_id SET NULL（FK ondelete）
"""

from __future__ import annotations

import secrets

import pytest_asyncio
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import App, CallLog, Channel, Provider, User
from chameleon.core.utils.passwords import hash_password
from chameleon.system.api_key.service import record_call


@pytest_asyncio.fixture
async def dims_fixture():
    """临时 app + user + provider + channel（FK 前置）"""
    suffix = secrets.token_hex(3)
    app_key = f"dims-app-{suffix}"

    async with AsyncSessionLocal() as s:
        app = App(app_key=app_key, name="dims test", status="active")
        s.add(app)
        user = User(
            username=f"dims-user-{suffix}",
            password_hash=hash_password("Pwd123!xx"),
            status="active",
            must_change_password=False,
        )
        s.add(user)
        provider = Provider(code=f"dims-prov-{suffix}", kind="llm", name="dims prov")
        s.add(provider)
        await s.flush()
        channel = Channel(provider_id=provider.id, name="dims-ch")
        s.add(channel)
        await s.flush()
        ids = {
            "app_key": app_key,
            "user_id": user.id,
            "provider_id": provider.id,
            "channel_id": channel.id,
        }
        await s.commit()

    yield ids

    async with AsyncSessionLocal() as s:
        await s.execute(delete(CallLog).where(CallLog.app_id == app_key))
        await s.execute(delete(App).where(App.app_key == app_key))
        await s.execute(delete(Channel).where(Channel.id == ids["channel_id"]))
        await s.execute(delete(Provider).where(Provider.id == ids["provider_id"]))
        await s.execute(delete(User).where(User.id == ids["user_id"]))
        await s.commit()


async def _fetch(request_id: str) -> CallLog:
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(
                select(CallLog).where(CallLog.request_id == request_id)
            )
        ).scalar_one()


async def test_record_call_persists_dims(dims_fixture: dict):
    rid = f"dims-rid-{secrets.token_hex(3)}"
    async with AsyncSessionLocal() as s:
        await record_call(
            s,
            request_id=rid,
            app_id=dims_fixture["app_key"],
            agent_key="example",
            session_id=None,
            stream=False,
            success=True,
            code=200,
            error_message=None,
            duration_ms=120,
            user_id=dims_fixture["user_id"],
            model_code="gpt-4o-mini",
            channel_id=dims_fixture["channel_id"],
        )
        await s.commit()

    row = await _fetch(rid)
    assert row.user_id == dims_fixture["user_id"]
    assert row.model_code == "gpt-4o-mini"
    assert row.channel_id == dims_fixture["channel_id"]


async def test_record_call_dims_default_null(dims_fixture: dict):
    """不传维度 → 三列 NULL（老调用方零改动）"""
    rid = f"dims-null-{secrets.token_hex(3)}"
    async with AsyncSessionLocal() as s:
        await record_call(
            s,
            request_id=rid,
            app_id=dims_fixture["app_key"],
            agent_key="example",
            session_id=None,
            stream=False,
            success=True,
            code=200,
            error_message=None,
            duration_ms=80,
        )
        await s.commit()

    row = await _fetch(rid)
    assert row.user_id is None
    assert row.model_code is None
    assert row.channel_id is None


async def test_channel_delete_sets_null(dims_fixture: dict):
    """删 channel → call_log.channel_id SET NULL（不级联删 call_log）"""
    rid = f"dims-fk-{secrets.token_hex(3)}"
    async with AsyncSessionLocal() as s:
        await record_call(
            s,
            request_id=rid,
            app_id=dims_fixture["app_key"],
            agent_key="example",
            session_id=None,
            stream=False,
            success=True,
            code=200,
            error_message=None,
            duration_ms=60,
            channel_id=dims_fixture["channel_id"],
        )
        await s.commit()

    # 物理删 channel（绕过 soft delete 验证 FK ondelete）
    async with AsyncSessionLocal() as s:
        await s.execute(
            delete(Channel).where(Channel.id == dims_fixture["channel_id"])
        )
        await s.commit()

    row = await _fetch(rid)
    assert row.channel_id is None
