"""admin 业务服务

- list_call_logs：四维过滤（app/agent/时间窗/状态）
- providers_status：遍历 PROVIDERS 调 healthcheck（不缓存，v1 简版）
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.app.modules.admin.schemas import CallLogItem, ProviderStatusItem
from chameleon.core.models import CallLog
from chameleon.core.response import PageParams, PageResult
from chameleon.providers.base import PROVIDERS


async def list_call_logs(
    session: AsyncSession,
    page: PageParams,
    *,
    app_id: str | None = None,
    agent_key: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    success: bool | None = None,
) -> PageResult[CallLogItem]:
    stmt = select(CallLog)
    if app_id is not None:
        stmt = stmt.where(CallLog.app_id == app_id)
    if agent_key is not None:
        stmt = stmt.where(CallLog.agent_key == agent_key)
    if since is not None:
        stmt = stmt.where(CallLog.created_at >= since)
    if until is not None:
        stmt = stmt.where(CallLog.created_at <= until)
    if success is not None:
        stmt = stmt.where(CallLog.success.is_(success))

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()

    rows = (
        (
            await session.execute(
                stmt.order_by(CallLog.created_at.desc())
                .offset(page.offset)
                .limit(page.limit)
            )
        )
        .scalars()
        .all()
    )

    return PageResult(
        items=[CallLogItem.model_validate(r) for r in rows],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


async def providers_status() -> list[ProviderStatusItem]:
    items: list[ProviderStatusItem] = []
    for name, provider in PROVIDERS.items():
        try:
            ok = await provider.healthcheck()
            items.append(ProviderStatusItem(name=name, ok=bool(ok)))
        except Exception as e:  # noqa: BLE001
            items.append(ProviderStatusItem(name=name, ok=False, error=str(e)))
    return items
