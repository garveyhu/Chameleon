"""审计上下文依赖

把"当前用户 + 请求来源"信息收敛成一个可注入对象，供 admin 写操作端点
调 write_audit_log 时填 actor / ip / user_agent / request_id。

只用于 JWT 鉴权的 /v1/admin/* 端点（app-key 调用方没有 actor，不审计）。
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request

from chameleon.system.auth.dependencies import CurrentUser, get_current_user


@dataclass(frozen=True)
class AuditContext:
    actor_user_id: int
    actor_username: str
    ip: str | None
    user_agent: str | None
    request_id: str | None


async def get_audit_context(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> AuditContext:
    """FastAPI 依赖：拼出审计上下文。"""
    return AuditContext(
        actor_user_id=user.id,
        actor_username=user.username,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
    )
