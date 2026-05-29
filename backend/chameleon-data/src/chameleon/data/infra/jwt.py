"""JWT 双 token（access 短 + refresh 长）+ Redis 黑名单

按 redesign.md §2.3：
- access_token  TTL 15min  Authorization: Bearer 头，Redis 可黑名单（按 jti）
- refresh_token TTL 7d     HTTP-only cookie，Redis 可黑名单（按 jti）

JWT secret 来自环境变量：CHAMELEON_JWT_SECRET（base64 ≥ 32 字节）
算法：HS256（单实例 ok；多实例若要签名共享可切 RS256）

黑名单 key 形如：`chameleon:jwt:revoked:<jti>` value=1 TTL=token 剩余生命周期。
"""

from __future__ import annotations

import base64
import os
import secrets
import time
import uuid
from typing import Any, Literal

import jwt
from loguru import logger

from chameleon.data.infra.redis import get_redis

TokenType = Literal["access", "refresh"]

ACCESS_TTL_SECONDS = 15 * 60
REFRESH_TTL_SECONDS = 7 * 24 * 60 * 60

ALGO = "HS256"

# 仅 dev / test：固定 32 字节 demo secret（sha256("chameleon-jwt-dev-fixed-demo") 的 base64）
_DEMO_SECRET_B64 = "jy5TbvmTLGRvRjw9nnGtq_g7sJMyDbJw4A6LW1UFK64="


class JwtNotConfigured(Exception):
    """CHAMELEON_JWT_SECRET 未配置或非法"""


class JwtInvalidToken(Exception):
    """token 解码失败 / 过期 / 签名错 / 已被吊销"""


def init_jwt() -> None:
    """启动期调用：production 缺 secret fail-fast；dev 用 demo + warn。

    幂等。
    """
    if os.environ.get("CHAMELEON_JWT_SECRET"):
        return
    env = os.environ.get("CHAMELEON_ENV", "").lower()
    if env == "production":
        raise JwtNotConfigured(
            "production 必须设置 CHAMELEON_JWT_SECRET；生成方法：\n"
            "  python -c 'import secrets,base64; "
            "print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'"
        )
    os.environ["CHAMELEON_JWT_SECRET"] = _DEMO_SECRET_B64
    logger.warning(
        "CHAMELEON_JWT_SECRET 未设置，使用 dev demo secret（仅限开发）"
    )


def _get_secret() -> bytes:
    raw = os.environ.get("CHAMELEON_JWT_SECRET")
    if not raw:
        raise JwtNotConfigured("CHAMELEON_JWT_SECRET 未设置；启动前调用 init_jwt()")
    try:
        decoded = base64.urlsafe_b64decode(raw)
    except Exception as e:
        raise JwtNotConfigured(f"CHAMELEON_JWT_SECRET 非合法 base64: {e}") from e
    if len(decoded) < 32:
        raise JwtNotConfigured(
            f"CHAMELEON_JWT_SECRET 解码后 {len(decoded)} 字节，至少 32 字节"
        )
    return decoded


def _new_jti() -> str:
    """token 唯一 ID（黑名单 key 用）"""
    return uuid.uuid4().hex


def encode_access_token(
    *,
    user_id: int,
    username: str,
    roles: list[str] | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """颁发 access_token。返回 (token, jti)。"""
    now = int(time.time())
    jti = _new_jti()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "roles": roles or [],
        "type": "access",
        "iat": now,
        "exp": now + ACCESS_TTL_SECONDS,
        "jti": jti,
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, _get_secret(), algorithm=ALGO)
    return token, jti


def encode_refresh_token(
    *,
    user_id: int,
    username: str,
    password_version: int = 0,
) -> tuple[str, str]:
    """颁发 refresh_token；password_version 用于改密后批量失效。"""
    now = int(time.time())
    jti = _new_jti()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "type": "refresh",
        "pwv": password_version,
        "iat": now,
        "exp": now + REFRESH_TTL_SECONDS,
        "jti": jti,
    }
    token = jwt.encode(payload, _get_secret(), algorithm=ALGO)
    return token, jti


def decode_token(token: str, *, expected_type: TokenType | None = None) -> dict[str, Any]:
    """解码并验证签名 + 过期。

    Args:
        token: encode 出来的 jwt 字符串
        expected_type: 若指定则校验 payload.type 必须等于此值

    Raises:
        JwtInvalidToken: 任何验证失败
    """
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=[ALGO])
    except jwt.ExpiredSignatureError as e:
        raise JwtInvalidToken(f"token expired: {e}") from e
    except jwt.InvalidTokenError as e:
        raise JwtInvalidToken(f"invalid token: {e}") from e

    if expected_type and payload.get("type") != expected_type:
        raise JwtInvalidToken(
            f"token type mismatch: expected {expected_type}, got {payload.get('type')}"
        )
    return payload


# ── 黑名单（Redis） ────────────────────────────────────────


_REVOKE_KEY_PREFIX = "chameleon:jwt:revoked:"


def _revoke_key(jti: str) -> str:
    return f"{_REVOKE_KEY_PREFIX}{jti}"


async def revoke_token(jti: str, ttl_seconds: int) -> None:
    """把 jti 加入 Redis 黑名单，TTL 等于 token 剩余生命周期。"""
    if ttl_seconds <= 0:
        return
    client = get_redis()
    await client.set(_revoke_key(jti), "1", ex=ttl_seconds)


async def is_revoked(jti: str) -> bool:
    """检查 jti 是否在黑名单"""
    client = get_redis()
    val = await client.get(_revoke_key(jti))
    return val is not None


async def decode_token_with_blacklist(
    token: str,
    *,
    expected_type: TokenType | None = None,
) -> dict[str, Any]:
    """完整校验：签名 + 过期 + 黑名单"""
    payload = decode_token(token, expected_type=expected_type)
    jti = payload.get("jti")
    if jti and await is_revoked(jti):
        raise JwtInvalidToken(f"token revoked (jti={jti})")
    return payload


def generate_secret_b64() -> str:
    """工具：生成 32 字节随机 base64 secret，给运维人员用"""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
