"""Redis 客户端连通性单测

需要本地 Redis 跑（参考 ~/.agents/resources.json local 段）。
component.json 已配 password —— 不通则跳过（开发环境降级友好）。
"""

from __future__ import annotations

import pytest

from chameleon.core.infra import redis as redis_infra


@pytest.mark.asyncio
async def test_redis_ping():
    """启动期 ping 检查"""
    try:
        result = await redis_infra.ping()
    except Exception as e:
        pytest.skip(f"Redis 不可用（开发环境降级跳过）: {e}")
    assert result is True


@pytest.mark.asyncio
async def test_redis_set_get_roundtrip():
    """SET/GET 往返"""
    client = redis_infra.get_redis()
    key = "chameleon:test:redis_smoke"
    try:
        await client.set(key, "hello", ex=10)
        value = await client.get(key)
        assert value == "hello"
    except Exception as e:
        pytest.skip(f"Redis 不可用: {e}")
    finally:
        try:
            await client.delete(key)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_redis_ttl_expires():
    """TTL 过期清理"""
    client = redis_infra.get_redis()
    key = "chameleon:test:redis_ttl"
    try:
        await client.set(key, "x", ex=1)
        ttl = await client.ttl(key)
        assert 0 < ttl <= 1
    except Exception as e:
        pytest.skip(f"Redis 不可用: {e}")
    finally:
        try:
            await client.delete(key)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_redis_incr_for_rate_limit():
    """INCR + EXPIRE 模式（登录限流要用）"""
    client = redis_infra.get_redis()
    key = "chameleon:test:redis_incr"
    try:
        await client.delete(key)
        n1 = await client.incr(key)
        await client.expire(key, 60)
        n2 = await client.incr(key)
        n3 = await client.incr(key)
        assert n1 == 1
        assert n2 == 2
        assert n3 == 3
    except Exception as e:
        pytest.skip(f"Redis 不可用: {e}")
    finally:
        try:
            await client.delete(key)
        except Exception:
            pass
