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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    AccountDisabledError,
    JwtExpiredError,
    JwtInvalidError,
    JwtMissingError,
    PermissionDeniedError,
)
from chameleon.core.infra.db import get_session
from chameleon.core.infra.jwt import JwtInvalidToken, decode_token_with_blacklist
from chameleon.core.models import Membership
from chameleon.core.models.workspace import DEFAULT_WORKSPACE_ID
from chameleon.system.auth import service as auth_service


@dataclass(frozen=True)
class CurrentUser:
    """请求级当前登录用户上下文"""

    id: int
    username: str
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    raw_payload: dict | None = None  # 给 logout 黑名单 access jti 用
    # P19.3：multi-tenant 上下文
    # workspace_id：本次请求选定的 ws；None = admin 未指定 = 看全量
    workspace_id: int | None = None
    # workspace_scope：用户可访问的 ws 集合；None = admin 不限
    workspace_scope: frozenset[int] | None = None

    @property
    def is_admin(self) -> bool:
        """admin scope —— admin role 或 *:* 通配

        细粒度 seed 模式下，admin 角色 bind 到全部具体 perm 行（如 users:read），
        permissions 列表不含字面量 `*:*`，所以这里同时看 role code。
        """
        return "admin" in self.roles or "*:*" in self.permissions

    def workspace_filter_ids(self) -> frozenset[int] | None:
        """业务 query 过滤用：返回 ws id 集；None = 不过滤（admin 全量视角）"""
        if self.workspace_id is not None:
            return frozenset({self.workspace_id})
        return None if self.is_admin else self.workspace_scope


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
    x_workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    """解析 access_token → 装载 user + roles + permissions + workspace scope

    P19.3：从 memberships 表 load 用户可访问的 workspace 集合；
    可选 `X-Workspace-Id` header 让 admin 切到具体 ws 视角；
    非 admin 老用户（无 memberships）兜底为 DEFAULT_WORKSPACE_ID 防 lockout。

    Raises:
        JwtMissingError / JwtExpiredError / JwtInvalidError / AccountDisabledError
        PermissionDeniedError: X-Workspace-Id 非法或越权
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

    workspace_id, workspace_scope = await _resolve_workspace_scope(
        session,
        user_id,
        list(view.roles),
        list(view.permissions),
        x_workspace_id,
    )

    return CurrentUser(
        id=view.id,
        username=view.username,
        roles=list(view.roles),
        permissions=list(view.permissions),
        raw_payload=payload,
        workspace_id=workspace_id,
        workspace_scope=workspace_scope,
    )


async def _resolve_workspace_scope(
    session: AsyncSession,
    user_id: int,
    roles: list[str],
    permissions: list[str],
    x_workspace_id: str | None,
) -> tuple[int | None, frozenset[int] | None]:
    """计算 (workspace_id, workspace_scope) —— 见 CurrentUser docstring"""
    is_admin = "admin" in roles or "*:*" in permissions

    rows = (
        (
            await session.execute(
                select(Membership.workspace_id).where(
                    Membership.user_id == user_id
                )
            )
        )
        .scalars()
        .all()
    )
    ws_ids = frozenset(rows)

    # admin 无 memberships → scope=None 表示全量
    # 非 admin 无 memberships → 兜底 default workspace，避免 lockout
    if is_admin:
        scope: frozenset[int] | None = None
    elif ws_ids:
        scope = ws_ids
    else:
        scope = frozenset({DEFAULT_WORKSPACE_ID})

    # 解析 header
    requested: int | None = None
    if x_workspace_id is not None and x_workspace_id.lower() != "all":
        try:
            requested = int(x_workspace_id)
        except ValueError:
            raise PermissionDeniedError(
                message=f"非法 X-Workspace-Id: {x_workspace_id}"
            )
        if not is_admin and scope is not None and requested not in scope:
            raise PermissionDeniedError(
                message=f"无权访问 workspace {requested}"
            )

    # admin 未指定 → None；非 admin 未指定但只属 1 个 ws → 默认锁定那个 ws
    if requested is None and not is_admin and scope is not None and len(scope) == 1:
        requested = next(iter(scope))

    return requested, scope


async def get_current_user_optional(
    authorization: str | None = Header(default=None),
    x_workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser | None:
    """登录可选（如 /v1/auth/logout 没登录也允许）"""
    if not authorization:
        return None
    try:
        return await get_current_user(
            authorization=authorization,
            x_workspace_id=x_workspace_id,
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
