"""auth HTTP 路由

挂点：/v1/auth/*
- POST /login   登录
- POST /refresh refresh token 旋转
- POST /logout  登出（黑名单 access + refresh）
- GET  /me      当前用户信息（含角色 + 权限点）
- POST /change-password           已登录改密
- POST /first-change-password     首次登录改密（must_change_password=True 时用）
"""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.core.infra.db import get_session
from chameleon.core.infra.jwt import REFRESH_TTL_SECONDS
from chameleon.system.auth import service
from chameleon.system.auth.dependencies import (
    CurrentUser,
    get_current_user,
    get_current_user_optional,
)
from chameleon.system.auth.rate_limit import check_login_rate
from chameleon.system.auth.schemas import (
    ChangePasswordRequest,
    CurrentUserView,
    FirstPasswordRequest,
    LoginRequest,
    TokenPair,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])

# refresh token cookie 名（HTTP-only，仅 /v1/auth 路径携带）
REFRESH_COOKIE = "chameleon_refresh"
REFRESH_COOKIE_PATH = "/v1/auth"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        max_age=REFRESH_TTL_SECONDS,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        samesite="lax",
        # secure=True 生产必开（HTTPS）；dev 默认 False
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


@router.post("/login", response_model=Result[TokenPair])
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> Result[TokenPair]:
    """密码登录

    成功：返 access_token；refresh_token 写 HTTP-only cookie
    失败：LoginFailedError（计数 +1）/ AccountDisabledError / LoginRateLimitError
    """
    ip = request.client.host if request.client else "unknown"
    rate_key = f"{ip}:{req.username}"
    await check_login_rate(rate_key)

    pair, refresh, _user = await service.login(
        session,
        username=req.username,
        password=req.password,
        rate_key=rate_key,
    )
    _set_refresh_cookie(response, refresh)
    return Result.ok(pair)


@router.post("/refresh", response_model=Result[TokenPair])
async def refresh(
    response: Response,
    chameleon_refresh: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    session: AsyncSession = Depends(get_session),
) -> Result[TokenPair]:
    """旋转 token；旧 refresh jti 进黑名单"""
    if not chameleon_refresh:
        from chameleon.core.api.exceptions import RefreshTokenInvalidError

        raise RefreshTokenInvalidError()
    pair, new_refresh = await service.refresh(session, refresh_token=chameleon_refresh)
    _set_refresh_cookie(response, new_refresh)
    return Result.ok(pair)


@router.post("/logout", response_model=Result[None])
async def logout(
    response: Response,
    user: CurrentUser | None = Depends(get_current_user_optional),
    chameleon_refresh: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
) -> Result[None]:
    """已登录 → 吊销 access + refresh；未登录也允许（清 cookie）"""
    await service.logout(
        access_payload=(user.raw_payload if user else None),
        refresh_token=chameleon_refresh,
    )
    _clear_refresh_cookie(response)
    return Result.ok(None)


@router.get("/me", response_model=Result[CurrentUserView])
async def me(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Result[CurrentUserView]:
    view = await service.me(session, user_id=user.id)
    return Result.ok(view)


@router.post("/change-password", response_model=Result[None])
async def change_password(
    req: ChangePasswordRequest,
    response: Response,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    chameleon_refresh: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
) -> Result[None]:
    """改密；password_version +1 → 所有旧 refresh 失效（含当前 cookie）"""
    await service.change_password(
        session,
        user_id=user.id,
        old_password=req.old_password,
        new_password=req.new_password,
        require_old=True,
    )
    # 当前 access 也吊销
    await service.logout(
        access_payload=user.raw_payload,
        refresh_token=chameleon_refresh,
    )
    _clear_refresh_cookie(response)
    return Result.ok(None)


@router.post("/first-change-password", response_model=Result[None])
async def first_change_password(
    req: FirstPasswordRequest,
    response: Response,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    chameleon_refresh: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
) -> Result[None]:
    """首次登录改密（不需要旧密码）"""
    await service.change_password(
        session,
        user_id=user.id,
        old_password=None,
        new_password=req.new_password,
        require_old=False,
    )
    await service.logout(
        access_payload=user.raw_payload,
        refresh_token=chameleon_refresh,
    )
    _clear_refresh_cookie(response)
    return Result.ok(None)
