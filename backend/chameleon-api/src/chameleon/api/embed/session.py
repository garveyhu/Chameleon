"""嵌入式 session_token 管理 + 限流

设计：
- session_token 不用 JWT（不需要持久 / 跨服务）—— 直接 Redis 短期 KV
- key: chameleon:embed:session:<token> = embed_config_id, TTL 1h
- 限流 key: chameleon:embed:ratelimit:<token>，5 msg/min（INCR + EXPIRE）
"""

from __future__ import annotations

import secrets

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.infra.redis import get_redis
from chameleon.core.utils.snowflake import next_session_id

SESSION_TTL_SECONDS = 60 * 60  # 1h
RATE_LIMIT_PER_MINUTE = 5

_SESSION_PREFIX = "chameleon:embed:session:"
_SID_PREFIX = "chameleon:embed:sid:"
_RATE_PREFIX = "chameleon:embed:ratelimit:"


def _token() -> str:
    return secrets.token_urlsafe(24)


def _session_key(token: str) -> str:
    return f"{_SESSION_PREFIX}{token}"


def _sid_key(token: str) -> str:
    return f"{_SID_PREFIX}{token}"


def _rate_key(token: str) -> str:
    return f"{_RATE_PREFIX}{token}"


async def create_session(embed_config_id: int) -> tuple[str, int]:
    """颁发新 session_token。返 (token, ttl_seconds)

    同时为该窗口绑定一个稳定的 session_id —— 同一 token 多轮调用共用，
    落 graph_runs / call_logs 时归为同一会话。
    """
    client = get_redis()
    token = _token()
    await client.set(_session_key(token), str(embed_config_id), ex=SESSION_TTL_SECONDS)
    await client.set(_sid_key(token), next_session_id(), ex=SESSION_TTL_SECONDS)
    return token, SESSION_TTL_SECONDS


async def resolve_session(token: str) -> int:
    """token → embed_config_id；过期 / 无效 → raise"""
    client = get_redis()
    raw = await client.get(_session_key(token))
    if raw is None:
        raise BusinessError(
            ResultCode.JwtInvalid, message="embed session 已过期或无效"
        )
    return int(raw)


async def resolve_session_id(token: str) -> str:
    """token → 绑定的会话 ID（同一窗口稳定）。

    老 token / 续期等情况下若缺失，则补发一个并续上 TTL，保证后续多轮稳定。
    """
    client = get_redis()
    sid = await client.get(_sid_key(token))
    if sid is not None:
        return sid
    fresh = next_session_id()
    await client.set(_sid_key(token), fresh, ex=SESSION_TTL_SECONDS)
    return fresh


async def check_rate_limit(token: str) -> None:
    """每个 session_token 每分钟最多 5 次 invoke；超过 raise"""
    client = get_redis()
    key = _rate_key(token)
    n = await client.incr(key)
    if n == 1:
        await client.expire(key, 60)
    if n > RATE_LIMIT_PER_MINUTE:
        raise BusinessError(
            ResultCode.AppRateLimit,
            message=f"嵌入式调用频率超限（{RATE_LIMIT_PER_MINUTE}/min）",
        )
