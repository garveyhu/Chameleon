"""Channel 健康周期维护（P23.C6）—— fail_count 半衰 + auto_disabled 冷却恢复

实时路径（routing.router.mark_failed）只会让 fail_count 单调上升、超阈值 disable；
没有自愈机制 → 偶发抖动会永久累积、被自动停用的 channel 永不回来。

本 job 由 cron 每 5min 跑：
1. **fail_count 半衰**：ENABLED channel 距上次失败已超 decay 窗口 → fail_count //= 2，
   让偶发失败随时间淡出，不会被几次零星抖动顶到阈值。
2. **冷却恢复**：AUTO_DISABLED channel 距上次失败已超 cooldown → 重新 ENABLED +
   fail_count 归 0，给它一次探测机会；若仍坏，实时路径会再次把它 disable
   （"连续失败 disable" 仍由 mark_failed 兜底）。

MANUAL_DISABLED 不在两条规则的过滤范围内 —— 管理员手停的不自动恢复。
纯 DB 逻辑（bulk UPDATE），可单测；不碰 Redis、不依赖 scheduler。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.models import Channel
from chameleon.core.models.channel import ChannelStatus

#: 距上次失败超过该分钟数才衰减 fail_count（避免刚失败就被抹平）
DECAY_AFTER_MINUTES = 5
#: AUTO_DISABLED channel 冷却该分钟数后重新启用探测
RECOVER_AFTER_MINUTES = 5


async def decay_and_recover_channels(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    decay_after_minutes: int = DECAY_AFTER_MINUTES,
    recover_after_minutes: int = RECOVER_AFTER_MINUTES,
) -> dict[str, int]:
    """跑一轮健康维护：衰减 fail_count + 恢复冷却到期的 auto_disabled channel

    Returns:
        {"decayed": 衰减条数, "recovered": 恢复条数}
    """
    now = now or datetime.now(timezone.utc)
    decayed = await _decay_fail_counts(session, now, decay_after_minutes)
    recovered = await _recover_auto_disabled(session, now, recover_after_minutes)
    await session.commit()
    if decayed or recovered:
        logger.info(
            "channel health | decayed={} | recovered={}", decayed, recovered
        )
    return {"decayed": decayed, "recovered": recovered}


async def _decay_fail_counts(
    session: AsyncSession, now: datetime, after_minutes: int
) -> int:
    cutoff = now - timedelta(minutes=after_minutes)
    stmt = (
        update(Channel)
        .where(
            Channel.status == ChannelStatus.ENABLED.value,
            Channel.fail_count > 0,
            Channel.deleted_at.is_(None),
            or_(
                Channel.last_failed_at.is_(None),
                Channel.last_failed_at <= cutoff,
            ),
        )
        # 整数列 / 2 → PG 整数除法（5→2→1→0）
        .values(fail_count=Channel.fail_count / 2)
    )
    result = await session.execute(stmt)
    return result.rowcount or 0


async def _recover_auto_disabled(
    session: AsyncSession, now: datetime, after_minutes: int
) -> int:
    cutoff = now - timedelta(minutes=after_minutes)
    stmt = (
        update(Channel)
        .where(
            Channel.status == ChannelStatus.AUTO_DISABLED.value,
            Channel.deleted_at.is_(None),
            or_(
                Channel.last_failed_at.is_(None),
                Channel.last_failed_at <= cutoff,
            ),
        )
        .values(status=ChannelStatus.ENABLED.value, fail_count=0)
    )
    result = await session.execute(stmt)
    return result.rowcount or 0
