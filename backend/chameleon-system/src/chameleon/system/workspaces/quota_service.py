"""workspace 配额服务 —— P19.3 PR #39

业务：
- 请求维度（request_quota_daily）：每天请求数上限；invoke 入口 check + increment
- token 维度（token_quota_monthly）：每月 token 上限；record_call 时 increment

红线（plan §2）：
- ⛔ 配额检查走单点（CurrentApp 鉴权 dep）—— 业务路由不分散写判定
- ⛔ 月度 / 日度 reset 用 reset_at + 跨期重置；不依赖系统时钟漂移
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.infra.redis import get_redis
from chameleon.core.models import App, WorkspaceQuota
from chameleon.core.models.workspace import DEFAULT_WORKSPACE_ID
from chameleon.core.observe import post_consume, pre_consume


@dataclass(frozen=True)
class QuotaSnapshot:
    """配额状态快照（含 used / limit + 是否超限）"""

    workspace_id: int
    token_quota_monthly: int | None
    token_used_current_month: int
    request_quota_daily: int | None
    request_used_today: int
    reset_at: datetime

    @property
    def token_exhausted(self) -> bool:
        return (
            self.token_quota_monthly is not None
            and self.token_used_current_month >= self.token_quota_monthly
        )

    @property
    def request_exhausted(self) -> bool:
        return (
            self.request_quota_daily is not None
            and self.request_used_today >= self.request_quota_daily
        )


# ── 配额查询 ────────────────────────────────────────────


async def get_or_create_quota(
    session: AsyncSession, workspace_id: int
) -> WorkspaceQuota:
    """读 workspace_quotas；不存在则惰性 seed（兼容老 workspace 无 quota 行）"""
    row = (
        await session.execute(
            select(WorkspaceQuota).where(
                WorkspaceQuota.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = WorkspaceQuota(
        workspace_id=workspace_id, reset_at=datetime.now(timezone.utc)
    )
    session.add(row)
    await session.flush()
    return row


async def snapshot(
    session: AsyncSession, workspace_id: int
) -> QuotaSnapshot:
    row = await get_or_create_quota(session, workspace_id)
    return QuotaSnapshot(
        workspace_id=row.workspace_id,
        token_quota_monthly=row.token_quota_monthly,
        token_used_current_month=row.token_used_current_month,
        request_quota_daily=row.request_quota_daily,
        request_used_today=row.request_used_today,
        reset_at=row.reset_at,
    )


# ── 配额检查（业务入口调） ──────────────────────────────


async def assert_within_request_quota(
    session: AsyncSession, workspace_id: int | None
) -> None:
    """invoke 入口前 check：超限 raise BusinessError(WorkspaceQuotaExceeded)

    workspace_id=None → admin 全量视角，跳过（不做配额检查）；
    租户表是宽容的，业务路径通常都能拿到具体 ws_id。
    """
    if workspace_id is None:
        return
    await _maybe_reset_periods(session, workspace_id)
    snap = await snapshot(session, workspace_id)
    if snap.request_exhausted:
        raise BusinessError(
            ResultCode.WorkspaceQuotaExceeded,
            message=(
                f"workspace #{workspace_id} 今日请求配额已用尽 "
                f"({snap.request_used_today}/{snap.request_quota_daily})"
            ),
        )
    if snap.token_exhausted:
        raise BusinessError(
            ResultCode.WorkspaceQuotaExceeded,
            message=(
                f"workspace #{workspace_id} 本月 token 配额已用尽 "
                f"({snap.token_used_current_month}/{snap.token_quota_monthly})"
            ),
        )


# ── 预扣 / 结算（C3/C4：invoke 入口预扣，record_call 末尾结算） ────────


async def pre_consume_request(
    session: AsyncSession,
    workspace_id: int | None,
    *,
    estimated_tokens: int,
    request_id: str,
) -> None:
    """invoke 入口预扣：按预估 token 在 Redis 原子预扣（并发防超发）

    workspace_id=None → 不限额跳过。额度不足 → raise WorkspaceQuotaExceeded(429)。
    """
    if workspace_id is None:
        return
    snap = await snapshot(session, workspace_id)
    quota_remaining: int | None = None
    if snap.token_quota_monthly is not None:
        quota_remaining = max(
            0, snap.token_quota_monthly - snap.token_used_current_month
        )
    await pre_consume(
        get_redis(),
        session,
        workspace_id=workspace_id,
        estimated_tokens=estimated_tokens,
        quota_remaining=quota_remaining,
        request_id=request_id,
    )


async def settle_request(
    session: AsyncSession,
    workspace_id: int | None,
    *,
    request_id: str,
) -> None:
    """record_call 末尾结算：释放本次请求预扣（实际用量由 increment_usage 落 SQL）

    best-effort：不抛错污染主路径（post_consume 内部已吞 Redis 错）。
    """
    if workspace_id is None:
        return
    await post_consume(get_redis(), workspace_id=workspace_id, request_id=request_id)


# ── 配额累加（record_call 后调） ────────────────────────


async def increment_usage(
    session: AsyncSession,
    workspace_id: int | None,
    *,
    total_tokens: int | None = None,
    requests: int = 1,
) -> None:
    """原子累加 used —— 不存在则惰性 seed。"""
    if workspace_id is None:
        return
    await get_or_create_quota(session, workspace_id)  # ensure row exists
    values: dict = {}
    if requests:
        values["request_used_today"] = (
            WorkspaceQuota.request_used_today + requests
        )
    if total_tokens:
        values["token_used_current_month"] = (
            WorkspaceQuota.token_used_current_month + total_tokens
        )
    if not values:
        return
    await session.execute(
        update(WorkspaceQuota)
        .where(WorkspaceQuota.workspace_id == workspace_id)
        .values(**values)
    )


# ── 跨期 reset（cron 调 + check 时兜底） ──────────────────


async def _maybe_reset_periods(
    session: AsyncSession, workspace_id: int
) -> None:
    """check 入口 lazy reset —— 防 cron 失约时计数不刷的兜底"""
    row = await get_or_create_quota(session, workspace_id)
    now = datetime.now(timezone.utc)
    reset_at = row.reset_at
    if reset_at.tzinfo is None:
        reset_at = reset_at.replace(tzinfo=timezone.utc)

    new_request = row.request_used_today
    new_token = row.token_used_current_month

    if reset_at.date() != now.date():
        new_request = 0
    if (reset_at.year, reset_at.month) != (now.year, now.month):
        new_token = 0

    if new_request != row.request_used_today or new_token != row.token_used_current_month:
        await session.execute(
            update(WorkspaceQuota)
            .where(WorkspaceQuota.workspace_id == workspace_id)
            .values(
                request_used_today=new_request,
                token_used_current_month=new_token,
                reset_at=now,
            )
        )
        logger.info(
            "quota reset | ws={} | req_used={}→{} | tok_used={}→{}",
            workspace_id,
            row.request_used_today,
            new_request,
            row.token_used_current_month,
            new_token,
        )


async def reset_all_periods(session: AsyncSession) -> int:
    """cron 入口：扫所有 quota 行触发 reset 检查；返跨期重置的行数"""
    rows = (
        (await session.execute(select(WorkspaceQuota))).scalars().all()
    )
    affected = 0
    now = datetime.now(timezone.utc)
    for r in rows:
        reset_at = r.reset_at
        if reset_at.tzinfo is None:
            reset_at = reset_at.replace(tzinfo=timezone.utc)
        crossed = reset_at.date() != now.date() or (
            reset_at.year,
            reset_at.month,
        ) != (now.year, now.month)
        if crossed:
            await _maybe_reset_periods(session, r.workspace_id)
            affected += 1
    if affected:
        await session.commit()
    return affected


# ── workspace 解析：从 app_id → workspace_id（业务 invoke 路径用） ──


async def workspace_id_for_app(
    session: AsyncSession, app_id: str
) -> int:
    """业务路径常用：app_id（即 App.app_key slug）→ workspace_id"""
    row = (
        await session.execute(
            select(App.workspace_id).where(App.app_key == app_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return DEFAULT_WORKSPACE_ID
    return row if row is not None else DEFAULT_WORKSPACE_ID
