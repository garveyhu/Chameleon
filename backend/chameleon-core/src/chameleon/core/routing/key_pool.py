"""多 key 池 —— 单 channel 多上游 key 的 round-robin + 失败隔离（P23.C7）

借鉴 one-api channel 多 key：一个 channel 配 N 个 key，请求间用 Redis 环形队列
（RPOPLPUSH）轮转分摊；某个 key 失败（401/限流等）就隔离一段时间，轮转时跳过，
TTL 到自动复活。

channel.keys 为空 → 退回单 key（api_key_encrypted）。Redis 不可达 → 退回首个 key，
绝不让请求拿不到凭证。
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger
from redis.asyncio import Redis
from redis.exceptions import RedisError

from chameleon.core.models import Channel
from chameleon.core.utils.crypto import get_or_decrypt

_POOL_PREFIX = "chameleon:keypool:"
_QUARANTINE_PREFIX = "chameleon:keypool:quarantine:"
# 环形队列 TTL（远大于请求间隔；keys 变更时按长度自动重建）
_POOL_TTL_SECONDS = 86400
# 失败 key 隔离时长
QUARANTINE_TTL_SECONDS = 300

_LUA_PATH = (
    Path(__file__).resolve().parents[1]
    / "infra"
    / "redis_scripts"
    / "keypool_next.lua"
)
_KEYPOOL_LUA = _LUA_PATH.read_text(encoding="utf-8")


def pool_list_key(channel_id: int) -> str:
    return f"{_POOL_PREFIX}{channel_id}"


def quarantine_set_key(channel_id: int) -> str:
    return f"{_QUARANTINE_PREFIX}{channel_id}"


async def next_key_index(redis: Redis, channel_id: int, pool_size: int) -> int:
    """round-robin 取下一个未隔离的 key 下标（Lua 原子）；不可达退 0"""
    if pool_size <= 0:
        return 0
    try:
        idx = await redis.eval(
            _KEYPOOL_LUA,
            2,
            pool_list_key(channel_id),
            quarantine_set_key(channel_id),
            pool_size,
            _POOL_TTL_SECONDS,
        )
        idx = int(idx)
        return idx if 0 <= idx < pool_size else 0
    except RedisError:
        logger.warning(
            "key_pool Redis 不可达，退回首 key | channel_id={}", channel_id
        )
        return 0


async def select_channel_key(
    redis: Redis, channel: Channel
) -> tuple[int | None, str | None]:
    """为 channel 选一个 key

    Returns:
        (key_index, decrypted_key)
        - channel.keys 非空 → 轮转选池中一个 key，key_index 为其下标
        - 否则 → 退回单 key（api_key_encrypted），key_index = None
    """
    keys = channel.keys or []
    if keys:
        idx = await next_key_index(redis, channel.id, len(keys))
        idx = idx if 0 <= idx < len(keys) else 0
        return idx, get_or_decrypt(keys[idx])
    # 单 key 回退
    return None, get_or_decrypt(channel.api_key_encrypted)


async def quarantine_key(
    redis: Redis,
    channel_id: int,
    key_index: int,
    *,
    ttl: int = QUARANTINE_TTL_SECONDS,
) -> None:
    """隔离一个失败 key（轮转时跳过）—— best-effort，不可达只 warn"""
    if key_index is None or key_index < 0:
        return
    try:
        qkey = quarantine_set_key(channel_id)
        await redis.sadd(qkey, key_index)
        await redis.expire(qkey, ttl)
    except RedisError:
        logger.warning(
            "key_pool 隔离失败（忽略）| channel_id={} | idx={}",
            channel_id,
            key_index,
        )
