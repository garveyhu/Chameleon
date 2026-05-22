"""P17.C1 record_call + observe 集成测试

验证 record_call 接受 observation 字段 + observe context 提供 parent_id 继承。
"""

from __future__ import annotations

import secrets

import pytest_asyncio
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import App, CallLog
from chameleon.core.observe import ObservationType, observe
from chameleon.system.api_key.service import record_call


@pytest_asyncio.fixture
async def tmp_app():
    """临时 app，测试完清理（含其下的 call_logs）"""
    suffix = secrets.token_hex(3)
    app_key = f"obs-app-{suffix}"
    async with AsyncSessionLocal() as s:
        a = App(app_key=app_key, name="obs test", status="active")
        s.add(a)
        await s.flush()
        await s.commit()
    yield app_key
    async with AsyncSessionLocal() as s:
        await s.execute(delete(CallLog).where(CallLog.app_id == app_key))
        await s.execute(delete(App).where(App.app_key == app_key))
        await s.commit()


# ── record_call 接受新字段 ────────────────────────────────


async def test_record_call_with_observation_fields(tmp_app: str):
    rid = secrets.token_hex(8)
    async with AsyncSessionLocal() as s:
        await record_call(
            s,
            request_id=rid,
            app_id=tmp_app,
            agent_key="x",
            session_id=None,
            stream=False,
            success=True,
            code=200,
            error_message=None,
            duration_ms=42,
            parent_id="root-id",
            observation_type="generation",
            completion_start_ms=100,
        )
        await s.commit()

    async with AsyncSessionLocal() as s:
        row = (
            await s.execute(select(CallLog).where(CallLog.request_id == rid))
        ).scalar_one()
        assert row.parent_id == "root-id"
        assert row.observation_type == "generation"
        assert row.completion_start_ms == 100


async def test_record_call_default_observation_type(tmp_app: str):
    """不传 observation_type 应默认 generation（兼容老调用方）"""
    rid = secrets.token_hex(8)
    async with AsyncSessionLocal() as s:
        await record_call(
            s,
            request_id=rid,
            app_id=tmp_app,
            agent_key="x",
            session_id=None,
            stream=False,
            success=True,
            code=200,
            error_message=None,
            duration_ms=1,
        )
        await s.commit()

    async with AsyncSessionLocal() as s:
        row = (
            await s.execute(select(CallLog).where(CallLog.request_id == rid))
        ).scalar_one()
        assert row.observation_type == "generation"
        assert row.parent_id is None


# ── observe → record_call 嵌套关联 ─────────────────────────


async def test_observe_supplies_parent_for_record_call(tmp_app: str):
    """observe() 给 ObservationContext.parent_id，调用方原样传给 record_call"""
    root_rid = secrets.token_hex(8)
    child_rid = secrets.token_hex(8)

    async with observe(
        request_id=root_rid, observation_type=ObservationType.TRACE
    ) as outer:
        async with AsyncSessionLocal() as s:
            await record_call(
                s,
                request_id=outer.request_id,
                parent_id=outer.parent_id,  # None
                observation_type=outer.observation_type,
                app_id=tmp_app,
                agent_key="x",
                session_id=None,
                stream=False,
                success=True,
                code=200,
                error_message=None,
                duration_ms=10,
            )
            await s.commit()

        async with observe(
            request_id=child_rid, observation_type=ObservationType.GENERATION
        ) as inner:
            # 自动从 contextvar 继承 outer 作为 parent
            assert inner.parent_id == root_rid
            async with AsyncSessionLocal() as s:
                await record_call(
                    s,
                    request_id=inner.request_id,
                    parent_id=inner.parent_id,  # = root_rid
                    observation_type=inner.observation_type,
                    app_id=tmp_app,
                    agent_key="x",
                    session_id=None,
                    stream=False,
                    success=True,
                    code=200,
                    error_message=None,
                    duration_ms=20,
                )
                await s.commit()

    async with AsyncSessionLocal() as s:
        rows = {
            r.request_id: r
            for r in (
                await s.execute(
                    select(CallLog).where(
                        CallLog.request_id.in_([root_rid, child_rid])
                    )
                )
            )
            .scalars()
            .all()
        }
    assert rows[root_rid].parent_id is None
    assert rows[root_rid].observation_type == "trace"
    assert rows[child_rid].parent_id == root_rid
    assert rows[child_rid].observation_type == "generation"
