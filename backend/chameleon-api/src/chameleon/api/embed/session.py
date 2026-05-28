"""嵌入式 session_token 管理 + 限流（S10 扩展：绑定 end_user_id）

设计：
- session_token 不用 JWT —— 直接 Redis 短期 KV
- key: chameleon:embed:session:<token> = embed_config_id, TTL 1h
- key: chameleon:embed:eu:<token> = end_user_id（S10 新增）
- key: chameleon:embed:sid:<token> = session_id（同窗口稳定）
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
_EU_PREFIX = "chameleon:embed:eu:"
_SID_PREFIX = "chameleon:embed:sid:"
_RATE_PREFIX = "chameleon:embed:ratelimit:"


def _token() -> str:
    return secrets.token_urlsafe(24)


def _session_key(token: str) -> str:
    return f"{_SESSION_PREFIX}{token}"


def _eu_key(token: str) -> str:
    return f"{_EU_PREFIX}{token}"


def _sid_key(token: str) -> str:
    return f"{_SID_PREFIX}{token}"


def _rate_key(token: str) -> str:
    return f"{_RATE_PREFIX}{token}"


async def create_session(
    embed_config_id: int,
    *,
    end_user_id: str | None = None,
    session_id: str | None = None,
) -> tuple[str, str, int]:
    """颁发新 session_token。返 (token, session_id, ttl_seconds)

    S10：可以传入 end_user_id（来自 anonymous_device hash / external_user_id /
    signed_jwt sub），绑定到 token；后续 invoke / list_sessions 都按这个用户
    隔离。session_id 也可以显式传入（用于「在已有会话上颁发新 token」），
    缺省则签发新 session_id。
    """
    client = get_redis()
    token = _token()
    sid = session_id or next_session_id()
    await client.set(_session_key(token), str(embed_config_id), ex=SESSION_TTL_SECONDS)
    await client.set(_sid_key(token), sid, ex=SESSION_TTL_SECONDS)
    if end_user_id:
        await client.set(_eu_key(token), end_user_id, ex=SESSION_TTL_SECONDS)
    return token, sid, SESSION_TTL_SECONDS


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


async def resolve_end_user_id(token: str) -> str | None:
    """token → 绑定的 end_user_id（S10）；未绑定（老 token / anonymous_legacy）返 None"""
    client = get_redis()
    return await client.get(_eu_key(token))


async def rebind_session_id(token: str, new_session_id: str) -> None:
    """把 token 上绑的 session_id 切到指定 sid（S11 用于「切到旧会话」/「开新会话」）"""
    client = get_redis()
    await client.set(_sid_key(token), new_session_id, ex=SESSION_TTL_SECONDS)


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
