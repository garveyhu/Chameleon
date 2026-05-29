"""FastAPI dependency：JWT 解析 + RBAC 守卫

使用：
    @router.get("/v1/admin/users", dependencies=[Depends(require_permission("users:read"))])
    async def list_users(current: CurrentUser = Depends(get_current_user)):
        ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    AccountDisabledError,
    JwtExpiredError,
    JwtInvalidError,
    JwtMissingError,
    PermissionDeniedError,
)
from chameleon.data.infra.db import get_session
from chameleon.data.infra.jwt import JwtInvalidToken, decode_token_with_blacklist
from chameleon.system.auth import service as auth_service


@dataclass(frozen=True)
class CurrentUser:
    """请求级当前登录用户上下文"""

    id: int
    username: str
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    raw_payload: dict | None = None  # 给 logout 黑名单 access jti 用

    @property
    def is_admin(self) -> bool:
        """admin scope —— admin role 或 *:* 通配

        细粒度 seed 模式下，admin 角色 bind 到全部具体 perm 行（如 users:read），
        permissions 列表不含字面量 `*:*`，所以这里同时看 role code。
        """
        return "admin" in self.roles or "*:*" in self.permissions


# ── 解析 access_token ────────────────────────────────────


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        raise JwtMissingError()
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise JwtMissingError()
    return parts[1].strip()


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    """解析 access_token → 装载 user + roles + permissions

    Raises:
        JwtMissingError / JwtExpiredError / JwtInvalidError / AccountDisabledError
    """
    token = _extract_bearer(authorization)
    try:
        payload = await decode_token_with_blacklist(token, expected_type="access")
    except JwtInvalidToken as e:
        msg = str(e).lower()
        if "expired" in msg:
            raise JwtExpiredError() from e
        raise JwtInvalidError() from e

    user_id = int(payload["sub"])
    view = await auth_service.me(session, user_id=user_id)
    if view.status == "disabled":
        raise AccountDisabledError()

    return CurrentUser(
        id=view.id,
        username=view.username,
        roles=list(view.roles),
        permissions=list(view.permissions),
        raw_payload=payload,
    )


async def get_current_user_optional(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser | None:
    """登录可选（如 /v1/auth/logout 没登录也允许）"""
    if not authorization:
        return None
    try:
        return await get_current_user(
            authorization=authorization,
            session=session,
        )
    except Exception:
        return None


# ── RBAC 守卫 ─────────────────────────────────────────────


def require_role(*roles: str) -> Callable:
    """角色守卫：用户必须拥有 roles 中至少一个"""
    role_set = set(roles)

    async def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not role_set & set(user.roles):
            raise PermissionDeniedError(
                message=f"需要角色: {', '.join(sorted(role_set))}"
            )
        return user

    return _dep


def require_permission(*perms: str) -> Callable:
    """权限守卫：用户必须拥有 perms 中所有权限

    支持 wildcard：如 "*:*" 在角色权限里 → 全通过；"agents:*" → 任意 agents action 通过
    """
    needed = set(perms)

    def _has(user_perms: set[str], perm: str) -> bool:
        if "*:*" in user_perms or perm in user_perms:
            return True
        resource = perm.split(":", 1)[0]
        return f"{resource}:*" in user_perms

    async def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        user_set = set(user.permissions)
        missing = [p for p in needed if not _has(user_set, p)]
        if missing:
            raise PermissionDeniedError(
                message=f"缺少权限: {', '.join(sorted(missing))}"
            )
        return user

    return _dep
