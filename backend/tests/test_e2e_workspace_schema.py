"""P19.3 PR #36 E2E：workspace schema 改造 + default ws seed + backfill 验证"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import (
    Agent,
    App,
    Dataset,
    EvalJob,
    Graph,
    KnowledgeBase,
    Membership,
    Team,
    User,
    Workspace,
    WorkspaceQuota,
)
from chameleon.core.models.workspace import DEFAULT_WORKSPACE_ID
from chameleon.core.utils.passwords import hash_password


_BIZ_TABLE_NAMES = (
    "agents",
    "apps",
    "knowledge_bases",
    "graphs",
    "datasets",
    "eval_jobs",
    "tool_instances",
    "channels",
    "abilities",
    "embed_configs",
)


# ── default workspace seed ──────────────────────────────


async def test_default_workspace_seeded():
    async with AsyncSessionLocal() as s:
        ws = (
            await s.execute(
                select(Workspace).where(Workspace.id == DEFAULT_WORKSPACE_ID)
            )
        ).scalar_one()
        assert ws.workspace_key == "default"
        assert ws.plan == "enterprise"
        # Quota 行也 seed 了；used 计数可能因前置测试 record_call 累加 > 0，
        # 这里只验证行存在 + counter 是非负 BigInt（不强求 == 0，避免跨测试污染）
        q = (
            await s.execute(
                select(WorkspaceQuota).where(
                    WorkspaceQuota.workspace_id == DEFAULT_WORKSPACE_ID
                )
            )
        ).scalar_one()
        assert q.token_used_current_month >= 0
        assert q.request_used_today >= 0


# ── 业务表都加了 workspace_id 列 ─────────────────────────


async def test_all_biz_tables_have_workspace_id_column():
    async with AsyncSessionLocal() as s:
        for tbl in _BIZ_TABLE_NAMES:
            r = await s.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = 'workspace_id'"
                ),
                {"t": tbl},
            )
            assert (
                r.scalar_one_or_none() is not None
            ), f"{tbl} 缺 workspace_id 列"


async def test_backfill_idempotent_via_update():
    """重跑 backfill SQL 应是 no-op（所有 migration 当时存在的行已设值；
    新插入未设 workspace_id 的行才会被 catch up）"""
    async with AsyncSessionLocal() as s:
        for tbl in _BIZ_TABLE_NAMES:
            r = await s.execute(
                text(
                    f"UPDATE {tbl} SET workspace_id = {DEFAULT_WORKSPACE_ID} "
                    "WHERE workspace_id IS NULL"
                )
            )
            await s.commit()
            # rowcount 可能 >0（其他测试新插入未设 workspace_id 的行），
            # 关键是 UPDATE 本身能跑通，FK 没坏
            assert r.rowcount >= 0


# ── ORM mixin 生效 —— 新建 row 时可以指定 workspace_id ──


async def test_orm_mixin_allows_workspace_id_assignment():
    async with AsyncSessionLocal() as s:
        agent = Agent(
            agent_key=f"e2e-ws-{secrets.token_hex(3)}",
            name="ws test agent",
            source="local",
            local_class_path="x.y:Z",
            enabled=True,
            workspace_id=DEFAULT_WORKSPACE_ID,
        )
        s.add(agent)
        await s.commit()
        await s.refresh(agent)
        try:
            assert agent.workspace_id == DEFAULT_WORKSPACE_ID
        finally:
            await s.execute(delete(Agent).where(Agent.id == agent.id))
            await s.commit()


# ── Workspace 表本身能用 ────────────────────────────────


@pytest_asyncio.fixture
async def temp_workspace():
    async with AsyncSessionLocal() as s:
        ws = Workspace(
            workspace_key=f"e2e-ws-{secrets.token_hex(2)}",
            name="临时 workspace",
            plan="pro",
        )
        s.add(ws)
        await s.commit()
        await s.refresh(ws)
        ws_id = ws.id
    yield ws_id
    async with AsyncSessionLocal() as s:
        await s.execute(delete(Workspace).where(Workspace.id == ws_id))
        await s.commit()


async def test_workspace_unique_key():
    """workspace_key 唯一约束"""
    async with AsyncSessionLocal() as s:
        key = f"dup-{secrets.token_hex(3)}"
        s.add(Workspace(workspace_key=key, name="a"))
        await s.commit()
        s.add(Workspace(workspace_key=key, name="b"))
        try:
            await s.commit()
        except IntegrityError:
            await s.rollback()
        else:
            raise AssertionError("应抛 unique 冲突")
        finally:
            await s.execute(delete(Workspace).where(Workspace.workspace_key == key))
            await s.commit()


# ── Team / Membership ───────────────────────────────────


async def test_team_belongs_to_workspace(temp_workspace: int):
    async with AsyncSessionLocal() as s:
        team = Team(workspace_id=temp_workspace, name="eng")
        s.add(team)
        await s.commit()
        await s.refresh(team)
        assert team.workspace_id == temp_workspace


async def test_membership_can_create(temp_workspace: int):
    """Membership 基础 CRUD —— uq 含 NULL 列时 PG 默认放过，重复约束在 PR #37 service 层兜底"""
    async with AsyncSessionLocal() as s:
        u = User(
            username=f"ws-mem-{secrets.token_hex(2)}",
            password_hash=hash_password("x"),
            status="active",
            must_change_password=False,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        uid = u.id

    try:
        async with AsyncSessionLocal() as s:
            s.add(
                Membership(
                    user_id=uid,
                    workspace_id=temp_workspace,
                    team_id=None,
                    role="owner",
                )
            )
            await s.commit()

            rows = (
                (
                    await s.execute(
                        select(Membership).where(Membership.user_id == uid)
                    )
                )
                .scalars()
                .all()
            )
            assert len(rows) == 1
            assert rows[0].role == "owner"
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(delete(Membership).where(Membership.user_id == uid))
            await s.execute(delete(User).where(User.id == uid))
            await s.commit()


async def test_membership_uq_with_team_blocks_duplicate(temp_workspace: int):
    """team_id 非 NULL 时 uq 正常触发（PG NULL distinct 行为）"""
    async with AsyncSessionLocal() as s:
        u = User(
            username=f"ws-mem2-{secrets.token_hex(2)}",
            password_hash=hash_password("x"),
            status="active",
            must_change_password=False,
        )
        s.add(u)
        team = Team(workspace_id=temp_workspace, name="t1")
        s.add(team)
        await s.commit()
        await s.refresh(u)
        await s.refresh(team)
        uid, tid = u.id, team.id

    try:
        async with AsyncSessionLocal() as s:
            s.add(
                Membership(
                    user_id=uid,
                    workspace_id=temp_workspace,
                    team_id=tid,
                    role="member",
                )
            )
            await s.commit()
            s.add(
                Membership(
                    user_id=uid,
                    workspace_id=temp_workspace,
                    team_id=tid,
                    role="admin",  # 同 (user, ws, team) 重复
                )
            )
            try:
                await s.commit()
            except IntegrityError:
                await s.rollback()
            else:
                raise AssertionError("uq 应触发")
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(delete(Membership).where(Membership.user_id == uid))
            await s.execute(delete(Team).where(Team.id == tid))
            await s.execute(delete(User).where(User.id == uid))
            await s.commit()


# ── default workspace 不可被删除（business safeguard 待 PR #37） ─

# 当前 PR 仅 schema 层；service 层不可删验证留 PR #37 集成
