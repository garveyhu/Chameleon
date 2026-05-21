"""auth 业务编排：登录 / 刷新 / 登出 / 改密 / me

规约：
- ORM 不出 service（CurrentUserView 等 DTO 才出去）
- 业务异常 raise（全局 handler 接管），不在这里 try/except 包响应
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chameleon.core.api.exceptions import (
    AccountDisabledError,
    LoginFailedError,
    RefreshTokenInvalidError,
)
from chameleon.core.infra.jwt import (
    ACCESS_TTL_SECONDS,
    REFRESH_TTL_SECONDS,
    decode_token,
    decode_token_with_blacklist,
    encode_access_token,
    encode_refresh_token,
    revoke_token,
)
from chameleon.core.models import Permission, Role, User
from chameleon.core.utils.passwords import (
    hash_password,
    needs_rehash,
    verify_password,
)
from chameleon.system.auth.rate_limit import (
    clear_login_attempts,
    record_login_failure,
)
from chameleon.system.auth.schemas import CurrentUserView, TokenPair

ACCOUNT_DISABLED = "disabled"


# ── 内部：查 user + 加载角色 / 权限 ────────────────────────


async def _load_user_with_perms(session: AsyncSession, user_id: int) -> User | None:
    """带 roles + permissions 一起 selectinload"""
    return (
        await session.execute(
            select(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
            .options(selectinload(User.roles).selectinload(Role.permissions))
        )
    ).scalar_one_or_none()


async def _load_user_by_username(
    session: AsyncSession, username: str
) -> User | None:
    return (
        await session.execute(
            select(User)
            .where(User.username == username, User.deleted_at.is_(None))
            .options(selectinload(User.roles).selectinload(Role.permissions))
        )
    ).scalar_one_or_none()


def _flatten_perms(user: User) -> list[str]:
    s: set[str] = set()
    for role in user.roles:
        for perm in role.permissions:
            s.add(perm.code)
    return sorted(s)


def _role_codes(user: User) -> list[str]:
    return sorted(r.code for r in user.roles)


# ── login ─────────────────────────────────────────────────


async def login(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    rate_key: str,
) -> tuple[TokenPair, str, User]:
    """密码登录

    Returns:
        (token_pair, refresh_token, user) —— refresh_token 由 API 层 set 进 cookie

    Raises:
        LoginFailedError: 用户名 / 密码不匹配（记一次失败计数）
        AccountDisabledError: 账号已停用（不记失败 —— 防止枚举活跃用户）
    """
    user = await _load_user_by_username(session, username)
    if user is None:
        await record_login_failure(rate_key)
        raise LoginFailedError()
    if user.status == ACCOUNT_DISABLED:
        raise AccountDisabledError()
    if not verify_password(password, user.password_hash):
        await record_login_failure(rate_key)
        raise LoginFailedError()

    # 旧 hash → 自动 rehash（不阻塞响应）
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.last_login_at = datetime.now(timezone.utc)
    await session.flush()

    # 颁发双 token
    access, _ = encode_access_token(
        user_id=user.id,
        username=user.username,
        roles=_role_codes(user),
    )
    refresh, _ = encode_refresh_token(
        user_id=user.id,
        username=user.username,
        password_version=user.password_version,
    )
    await clear_login_attempts(rate_key)

    logger.info("login success | user_id={} | username={}", user.id, user.username)
    return (
        TokenPair(access_token=access, expires_in=ACCESS_TTL_SECONDS),
        refresh,
        user,
    )


# ── refresh ──────────────────────────────────────────────


async def refresh(
    session: AsyncSession,
    *,
    refresh_token: str,
) -> tuple[TokenPair, str]:
    """旋转 refresh：吊销旧 jti，颁发新对。

    Raises:
        RefreshTokenInvalidError: token 无效 / 过期 / 被吊销 / password_version 不匹配
    """
    try:
        payload = await decode_token_with_blacklist(
            refresh_token, expected_type="refresh"
        )
    except Exception as e:
        logger.warning("refresh failed: {}", e)
        raise RefreshTokenInvalidError() from e

    user_id = int(payload["sub"])
    user = await _load_user_with_perms(session, user_id)
    if user is None or user.status == ACCOUNT_DISABLED:
        raise RefreshTokenInvalidError()
    if payload.get("pwv") != user.password_version:
        # 密码已改 → 旧 refresh 无效
        raise RefreshTokenInvalidError()

    # 旋转：吊销旧 jti
    old_jti = payload["jti"]
    await revoke_token(old_jti, ttl_seconds=REFRESH_TTL_SECONDS)

    access, _ = encode_access_token(
        user_id=user.id,
        username=user.username,
        roles=_role_codes(user),
    )
    new_refresh, _ = encode_refresh_token(
        user_id=user.id,
        username=user.username,
        password_version=user.password_version,
    )
    return TokenPair(access_token=access, expires_in=ACCESS_TTL_SECONDS), new_refresh


# ── logout ────────────────────────────────────────────────


async def logout(
    *,
    access_payload: dict[str, Any] | None,
    refresh_token: str | None,
) -> None:
    """吊销当前 access + refresh 的 jti。

    access_payload 由 dependency 已解码；refresh_token 来自 cookie（可能为 None）。
    """
    if access_payload:
        jti = access_payload.get("jti")
        if jti:
            await revoke_token(jti, ttl_seconds=ACCESS_TTL_SECONDS)
    if refresh_token:
        try:
            r_payload = decode_token(refresh_token, expected_type="refresh")
            await revoke_token(r_payload["jti"], ttl_seconds=REFRESH_TTL_SECONDS)
        except Exception:
            # cookie 里 refresh 已过期 / 非法 → 忽略
            pass


# ── change_password ──────────────────────────────────────


async def change_password(
    session: AsyncSession,
    *,
    user_id: int,
    old_password: str | None,
    new_password: str,
    require_old: bool = True,
) -> None:
    """改密

    require_old=False 用于 must_change_password 首次改密流程（已用临时密码登入）。
    密码版本号 +1 → 所有旧 refresh 自动失效。
    """
    user = await _load_user_with_perms(session, user_id)
    if user is None:
        raise LoginFailedError(message="账号不存在")
    if require_old:
        if not old_password or not verify_password(old_password, user.password_hash):
            raise LoginFailedError(message="旧密码错误")

    user.password_hash = hash_password(new_password)
    user.password_version = user.password_version + 1
    user.must_change_password = False
    await session.flush()
    logger.info("password changed | user_id={}", user_id)


# ── me ────────────────────────────────────────────────────


async def me(session: AsyncSession, *, user_id: int) -> CurrentUserView:
    user = await _load_user_with_perms(session, user_id)
    if user is None:
        raise AccountDisabledError(message="账号不存在")
    return CurrentUserView(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        locale=user.locale,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        roles=_role_codes(user),
        permissions=_flatten_perms(user),
    )
