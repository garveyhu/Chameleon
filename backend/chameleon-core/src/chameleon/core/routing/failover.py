"""Failover wrapper —— 包装 provider 调用，失败自动重试下一个 channel

接口设计：
```python
async def my_invoke(channel: Channel) -> Result:
    # 用 channel 凭证调 provider
    ...

result = await invoke_with_failover(
    session,
    model_code="gpt-4",
    group_id=None,
    max_retries=3,
    invoke_fn=my_invoke,
)
```

约束：
- 仅非流式调用全程包装；流式只能 wrap "建立连接 + 拿第一 chunk" 前阶段
- 每次失败：mark_failed（健康统计 + 超阈值自动 disable）
- 成功：mark_success（elapsed_ms 滑动平均 + reset fail_count）
- 全部 retries 用完：抛最后一个错误（不是 NoSatisfiedChannelError，而是真实的 ProviderError）
- 没找到任何可用 channel：抛 NoSatisfiedChannelError（路径上根本没起飞）
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.models import Channel
from chameleon.core.routing.error_classify import should_retry
from chameleon.core.routing.router import (
    NoSatisfiedChannelError,
    mark_failed,
    mark_success,
    resolve_channel,
)

T = TypeVar("T")


async def invoke_with_failover(
    session: AsyncSession,
    *,
    model_code: str,
    invoke_fn: Callable[[Channel], Awaitable[T]],
    group_id: int | None = None,
    max_retries: int = 3,
) -> tuple[T, Channel]:
    """包装一次 provider 调用 + 失败 failover

    Args:
        model_code: 路由 model_code（agent.preferred_model_code）
        invoke_fn: 给定 channel 后调 provider 的 callable，返实际结果
        group_id: 用户所属 group（None 表示走全局 ability）
        max_retries: 失败后最多重试 N 次（第一次也算一次尝试，所以总 N+1 次）

    Returns:
        (invoke_fn 的结果, 最终用的 channel)

    Raises:
        NoSatisfiedChannelError: 一开始就没找到任何 channel
        Exception: 重试用完后最后一次的原始异常
    """
    exclude: set[int] = set()
    last_exc: Exception | None = None
    attempts = 0
    total_tries = max_retries + 1

    while attempts < total_tries:
        attempts += 1
        # 选 channel（排除已失败的）
        try:
            channel = await resolve_channel(
                session,
                model_code=model_code,
                group_id=group_id,
                exclude_channels=exclude,
            )
        except NoSatisfiedChannelError:
            if last_exc is not None:
                # 之前有 channel 调用失败导致都被排除 → 抛最后一个真实错误
                raise last_exc
            raise

        start = time.monotonic()
        try:
            result = await invoke_fn(channel)
        except asyncio.CancelledError:
            # 用户主动取消 / 上游 timeout 强中断 → 不重试，不标失败
            raise
        except Exception as e:  # noqa: BLE001
            elapsed_ms = int((time.monotonic() - start) * 1000)
            last_exc = e
            exclude.add(channel.id)
            logger.warning(
                "failover attempt {}/{} failed | channel_id={} | elapsed_ms={} | "
                "err={}",
                attempts,
                total_tries,
                channel.id,
                elapsed_ms,
                type(e).__name__,
            )
            # 单独 transaction 写监控，避免污染主 session（best-effort）
            try:
                await mark_failed(session, channel.id)
            except Exception:  # noqa: BLE001
                logger.exception("mark_failed swallowed")

            if not should_retry(e):
                # 不可重试 → 直接抛（业务 / 输入级错误）
                raise

            if attempts >= total_tries:
                # 重试用完
                raise

            # 继续下一轮
            continue

        # 成功路径
        elapsed_ms = int((time.monotonic() - start) * 1000)
        try:
            await mark_success(session, channel.id, elapsed_ms=elapsed_ms)
        except Exception:  # noqa: BLE001
            logger.exception("mark_success swallowed")
        return result, channel

    # 理论上不可达 —— 上面 while 都有 raise
    if last_exc is not None:
        raise last_exc
    raise NoSatisfiedChannelError(model_code, message="failover exhausted")


async def build_channel_override(redis, channel: Channel) -> dict:
    """从 Channel 行构造 ChannelOverride 字段 dict（含本次选中的 key）

    多 key 池（channel.keys 非空）走 key_pool round-robin 轮转选一个 key；否则退回
    单 key（api_key_encrypted）。返回里多带一个 `key_index`：调用方在调用失败时据此
    `key_pool.quarantine_key` 隔离该 key（None 表示单 key 模式，无需隔离）。
    """
    from chameleon.core.routing.key_pool import select_channel_key

    key_index, api_key = await select_channel_key(redis, channel)
    return {
        "channel_id": channel.id,
        "base_url": channel.base_url,
        "api_key": api_key,
        "key_index": key_index,
    }
