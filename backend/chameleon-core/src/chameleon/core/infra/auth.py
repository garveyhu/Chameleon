"""API Key 鉴权

裁决 A12: plaintext = "chm_" + 40 字符 base62；hash = sha256(plaintext)；
       key_prefix 存前 12 字符（含 "chm_"）作为列表回显。

Bootstrap：第一个 admin key 由 CLI `chameleon init-admin` 落库（明文回显一次）。
之后所有 admin 接口通过 admin scope 的 api_key 鉴权。
"""

from __future__ import annotations

import hashlib
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Header
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.infra.db import get_session
from chameleon.core.infra.jwt import (
    JwtInvalidToken,
    decode_token_with_blacklist,
)
from chameleon.core.api.exceptions import (
    BusinessError,
    PermissionDeniedError,
    ResultCode,
)
from chameleon.core.models import ApiKey, App

_ALPHABET = string.ascii_letters + string.digits
_KEY_BODY_LEN = 40
_PREFIX_LEN = 12


@dataclass(frozen=True)
class CurrentApp:
    """请求级当前应用上下文（来自鉴权 middleware）"""

    id: int
    app_id: str
    name: str
    scopes: list[str]
    # P19.3 PR #39：app → workspace 归属，配额检查 / 业务过滤都靠这个
    workspace_id: int | None = None


# ── key 生成与校验 ────────────────────────────────────────


def generate_api_key() -> tuple[str, str, str]:
    """生成 (plaintext, hash, key_prefix)

    plaintext 仅一次回显，不存库；存 hash + prefix。
    """
    body = "".join(secrets.choice(_ALPHABET) for _ in range(_KEY_BODY_LEN))
    plaintext = f"chm_{body}"
    digest = hash_api_key(plaintext)
    prefix = plaintext[:_PREFIX_LEN]
    return plaintext, digest, prefix


def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


# ── FastAPI Depends ─────────────────────────────────────


async def current_app(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
) -> CurrentApp:
    """从 Authorization: Bearer 头解析当前应用

    缺失 → MissingApiKey；无效 → InvalidApiKey；已撤 → ApiKeyRevoked
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise BusinessError(ResultCode.MissingApiKey)
    plaintext = authorization.removeprefix("Bearer ").strip()
    if not plaintext:
        raise BusinessError(ResultCode.MissingApiKey)

    digest = hash_api_key(plaintext)
    row = (
        await session.execute(select(ApiKey).where(ApiKey.key_hash == digest))
    ).scalar_one_or_none()

    if row is None:
        raise BusinessError(ResultCode.InvalidApiKey)
    if row.revoked_at is not None:
        raise BusinessError(ResultCode.ApiKeyRevoked)

    # 更新 last_used_at（不阻塞响应——简单同步即可，QPS 不高）
    row.last_used_at = datetime.now(timezone.utc)
    # 不显式 commit，由 get_session 上下文管理

    # P19.3：解析 app_id（slug）→ workspace_id（业务路径配额 / 过滤靠这个）
    # ApiKey.app_id 存的是 App.app_key（slug），不是 App.id
    ws_id = (
        await session.execute(
            select(App.workspace_id).where(App.app_key == row.app_id)
        )
    ).scalar_one_or_none()

    logger.debug("auth ok | app_id={} | scopes={}", row.app_id, row.scopes)
    return CurrentApp(
        id=row.id,
        app_id=row.app_id,
        name=row.name,
        scopes=list(row.scopes or []),
        workspace_id=ws_id,
    )


async def current_app_or_admin(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
) -> CurrentApp:
    """业务 api_key OR admin JWT 双轨鉴权。

    admin UI（管理后台 / Playground / 对话查询）走 JWT；外部业务方走 api_key。
    JWT 解码成功 → 返合成 CurrentApp（scopes=["admin"]，workspace_id=None 全量视角）；
    否则交给 api_key 解析路径。
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise BusinessError(ResultCode.MissingApiKey)
    token = authorization.removeprefix("Bearer ").strip()
    # 先试 JWT（admin / user）
    try:
        payload = await decode_token_with_blacklist(token, expected_type="access")
        if payload.get("sub"):
            return CurrentApp(
                id=0,
                app_id="admin",
                name=payload.get("username") or "admin",
                scopes=["admin"],
                workspace_id=None,
            )
    except (JwtInvalidToken, Exception):
        pass
    # JWT 不通 → api_key 路径
    return await current_app(authorization=authorization, session=session)


def require_scope(scope: str):
    """Depends factory：要求 CurrentApp.scopes 包含指定 scope

    Example: `app = Depends(require_scope("admin"))`
    """

    async def _guard(app: CurrentApp = Depends(current_app)) -> CurrentApp:
        if scope not in app.scopes:
            if scope == "admin":
                raise PermissionDeniedError(ResultCode.AdminScopeRequired)
            # 通用：用 AgentNotInScope 兜底（细分由 ResultCode 自带）
            raise PermissionDeniedError(ResultCode.AgentNotInScope)
        return app

    return _guard
