"""登录速率限制（Redis-backed）

key: chameleon:login_attempts:<username 或 ip>
规则：5 次失败 → 锁定 15 分钟；成功登录清计数。
"""

from __future__ import annotations

from chameleon.core.api.exceptions import LoginRateLimitError
from chameleon.data.infra.redis import get_redis

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60  # 15 分钟

_KEY_PREFIX = "chameleon:login_attempts:"


def _key(identifier: str) -> str:
    return f"{_KEY_PREFIX}{identifier}"


async def check_login_rate(identifier: str) -> None:
    """登录前检查；超阈值 raise LoginRateLimitError"""
    client = get_redis()
    n = await client.get(_key(identifier))
    if n is not None and int(n) >= MAX_ATTEMPTS:
        raise LoginRateLimitError()


async def record_login_failure(identifier: str) -> int:
    """记一次失败 + 设置 / 续 TTL；返回当前计数"""
    client = get_redis()
    key = _key(identifier)
    n = await client.incr(key)
    if n == 1:
        await client.expire(key, LOCKOUT_SECONDS)
    return int(n)


async def clear_login_attempts(identifier: str) -> None:
    """成功登录后清计数"""
    client = get_redis()
    await client.delete(_key(identifier))
