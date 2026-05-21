"""Redis 异步客户端单例

用途（按 redesign.md §2.2）：
  1. JWT 黑名单（access token JTI 吊销）
  2. 登录速率限制（INCR + EXPIRE 计数器）
  3. 配置热重载缓存（models / providers / agents 30s TTL）
  4. 嵌入式 session_token 存储（1h TTL）

连接配置：来自 component.json 的 redis 段，详见 inventory.redis_config()。
"""

from __future__ import annotations

from typing import Any

import redis.asyncio as redis_async
from loguru import logger
from redis.asyncio import Redis

from chameleon.core.config import inventory


def _build_client() -> Redis:
    cfg: dict[str, Any] = inventory.redis_config()
    if not cfg:
        raise RuntimeError(
            "component.json 缺 redis 段 —— 请按 config/example/component.example.json 补齐"
        )

    host = cfg.get("host", "127.0.0.1")
    port = int(cfg.get("port", 6379))
    db = int(cfg.get("db", 0))
    password = cfg.get("password") or None
    socket_timeout = float(cfg.get("socket_timeout", 0.5))

    return redis_async.Redis(
        host=host,
        port=port,
        db=db,
        password=password,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_timeout,
        decode_responses=True,
        health_check_interval=30,
    )


# 模块导入即初始化（与 db.engine 一致的 lifecycle 模式）
redis_client: Redis = _build_client()


def get_redis() -> Redis:
    """FastAPI Depends 友好的获取器，方便测试时 monkey-patch"""
    return redis_client


async def ping() -> bool:
    """启动期连通性检查。失败抛 RedisConnectionError，由 lifespan 决定 fail-fast 还是 warn。"""
    try:
        pong = await redis_client.ping()
        return bool(pong)
    except Exception as e:
        logger.error("Redis ping failed: {}", e)
        raise


async def aclose() -> None:
    """lifespan shutdown 调用，释放连接池"""
    try:
        await redis_client.aclose()
    except Exception as e:
        logger.warning("Redis close error (ignored): {}", e)
