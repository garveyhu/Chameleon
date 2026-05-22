"""路由 service —— 按 model_code 解析到 channel + 健康监控写入

### 路由算法

1. **过滤**：abilities.enabled=True + channel.status='enabled' + channel 未软删
2. **作用域**：精确 group_id 匹配优先；都没匹配回退到 NULL group（全局）
3. **优先级**：同作用域内取最大 priority 的所有 ability
4. **加权随机**：同 priority 内按 ability.weight 加权随机；weight=0 视为等权
5. **排除集合**：调用方可传 exclude_channels（failover 重试时排除上一失败 channel）

### 健康监控

- `mark_success(channel_id, elapsed_ms)`：reset fail_count、更新 response_time_ms
  滑动平均、更新 last_success_at
- `mark_failed(channel_id, *, auto_disable_threshold=5)`：fail_count++、
  更新 last_failed_at；超阈值 → status='auto_disabled'

写操作都 best-effort（监控失败不影响主调用流程；上层在 finally 里调，
swallow Exception）。
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.models import Ability, Channel
from chameleon.core.models.channel import ChannelStatus


class NoSatisfiedChannelError(BusinessError):
    """model_code 没找到可用 channel —— 业务层应捕获并报 503/4xx 业务码"""

    def __init__(self, model_code: str, message: str | None = None) -> None:
        super().__init__(
            ResultCode.RegistryError,
            message=message or f"no enabled channel for model_code={model_code}",
        )


# ── 路由解析 ──────────────────────────────────────────────


async def resolve_channel(
    session: AsyncSession,
    *,
    model_code: str,
    group_id: int | None = None,
    exclude_channels: set[int] | None = None,
) -> Channel:
    """按 model_code 解析到一条可用 channel

    Args:
        model_code: 调用方声明的模型名（如 "qwen-plus", "gpt-4"）
        group_id: 调用方所属 group；None 时只看全局 ability
        exclude_channels: failover 重试时已失败的 channel 集合（排除）

    Returns:
        Channel ORM 实例（已确保 enabled + 未软删）

    Raises:
        NoSatisfiedChannelError: 没有任何可用 channel
    """
    exclude = exclude_channels or set()

    # 1) 优先尝试精确 group_id；找不到再退到 NULL group
    if group_id is not None:
        ch = await _try_resolve(
            session,
            model_code=model_code,
            group_filter=Ability.group_id == group_id,
            exclude=exclude,
        )
        if ch is not None:
            return ch

    # 2) NULL group_id 兜底（全局 ability）
    ch = await _try_resolve(
        session,
        model_code=model_code,
        group_filter=Ability.group_id.is_(None),
        exclude=exclude,
    )
    if ch is None:
        raise NoSatisfiedChannelError(model_code)
    return ch


async def _try_resolve(
    session: AsyncSession,
    *,
    model_code: str,
    group_filter,
    exclude: set[int],
) -> Channel | None:
    """在指定 group 作用域内尝试解析；查不到返 None（让上层 fallback）"""
    stmt = (
        select(Ability, Channel)
        .join(Channel, Ability.channel_id == Channel.id)
        .where(
            Ability.model_code == model_code,
            Ability.enabled.is_(True),
            group_filter,
            Channel.status == ChannelStatus.ENABLED.value,
            Channel.deleted_at.is_(None),
        )
    )
    if exclude:
        stmt = stmt.where(~Channel.id.in_(exclude))

    rows = (await session.execute(stmt)).all()
    if not rows:
        return None

    # 取最高 priority 那一档
    max_priority = max(a.priority for a, _ in rows)
    top = [(a, c) for a, c in rows if a.priority == max_priority]

    # 同 priority 多 channel → 按 ability.weight 加权随机
    # weight 放 ability 级别：同 channel 在不同 model_code 下可有不同权重
    if len(top) == 1:
        return top[0][1]
    weights = [max(a.weight, 0) for a, _ in top]
    if sum(weights) == 0:
        # 所有 weight=0 → 等权随机
        return random.choice(top)[1]
    return random.choices(top, weights=weights, k=1)[0][1]


# ── 健康监控 ──────────────────────────────────────────────


async def mark_success(
    session: AsyncSession,
    channel_id: int,
    *,
    elapsed_ms: int | None = None,
) -> None:
    """成功路径：reset fail_count、更新 last_success_at + p95（滑动平均）

    elapsed_ms 滑动平均权重：旧值 70% + 新值 30%（指数加权移动平均，简化版）
    """
    ch = (
        await session.execute(
            select(Channel).where(Channel.id == channel_id)
        )
    ).scalar_one_or_none()
    if ch is None:
        return
    ch.fail_count = 0
    ch.last_success_at = datetime.now(timezone.utc)
    if elapsed_ms is not None and elapsed_ms >= 0:
        if ch.response_time_ms is None:
            ch.response_time_ms = elapsed_ms
        else:
            ch.response_time_ms = int(
                ch.response_time_ms * 0.7 + elapsed_ms * 0.3
            )
    await session.flush()


async def mark_failed(
    session: AsyncSession,
    channel_id: int,
    *,
    auto_disable_threshold: int = 5,
) -> None:
    """失败路径：fail_count++、更新 last_failed_at；超阈值自动 disable

    auto_disable_threshold 默认 5 —— 连续 5 次失败视为该 channel 不健康。
    """
    ch = (
        await session.execute(
            select(Channel).where(Channel.id == channel_id)
        )
    ).scalar_one_or_none()
    if ch is None:
        return
    ch.fail_count = (ch.fail_count or 0) + 1
    ch.last_failed_at = datetime.now(timezone.utc)
    if (
        ch.fail_count >= auto_disable_threshold
        and ch.status == ChannelStatus.ENABLED.value
    ):
        ch.status = ChannelStatus.AUTO_DISABLED.value
    await session.flush()
