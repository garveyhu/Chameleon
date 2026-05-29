"""audit_log 写入 helper

设计：service 层在重要写操作完成后显式调（不挂全局中间件）。
理由：
- 全局中间件无法精确知道资源 id / before/after
- 失败回滚时不应该有 audit_log
- 显式调让代码 review 时一眼看出哪些操作有审计
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.data.models import AuditLog


async def write_audit_log(
    session: AsyncSession,
    *,
    actor_user_id: int | None,
    actor_username: str | None,
    action: str,
    resource_type: str,
    resource_id: str | int | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> None:
    """在当前 session 写一条 audit_log（不 commit）"""
    try:
        log = AuditLog(
            actor_user_id=actor_user_id,
            actor_username=actor_username,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            before=before,
            after=after,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
        )
        session.add(log)
        await session.flush()
    except Exception as e:
        logger.warning("audit_log write failed (ignored): {}", e)
