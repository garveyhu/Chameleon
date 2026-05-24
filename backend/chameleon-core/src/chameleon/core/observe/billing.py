"""配额预扣 / 返还（P23.C3 + C4）—— 借鉴 one-api relay pre/post-consume

问题：token 用量只在调用**完成后**才计入 SQL，并发场景下多个在途请求会各自
通过"配额未耗尽"的前置检查，合计把配额打穿。

方案（one-api 同款）：
- **pre-consume**：调用前按 prompt + 预估 completion 算一个估值，原子地在 Redis
  里"预扣"（reserved 计数）。在途预扣计入可用额度，挡住并发超发。
- **trust 阈值**：剩余额度远大于预估（> trust_multiplier × est）时**跳过预扣**
  ——这类用户额度充裕，省下 Redis 往返；post-consume 仍会把实际用量落 SQL。
- **post-consume**（见 release_reservation + recorder）：调用后释放本次预扣，
  实际用量由 quota_service.increment_usage 落 SQL。

降级（红线）：Lua 不可达 → SQL `SELECT … FOR UPDATE` 串行化兜底，**绝不让请求
fail**；此时不做持久预扣（Redis 才是预扣存储），仅在 SQL 已显示耗尽时拒绝。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from loguru import logger
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.models import WorkspaceQuota

# reserved key 前缀（与项目既有 chameleon: 命名一致）
_RESERVED_PREFIX = "chameleon:billing:reserved:"
# 单请求预扣标记前缀：记下本次请求预扣了多少，post-consume 据此精确释放
_RESERVED_REQ_PREFIX = "chameleon:billing:reserved:req:"
# 剩余额度 > 该倍数 × 预估 → 信任跳过预扣
DEFAULT_TRUST_MULTIPLIER = 100
# reserved key TTL：请求崩溃 / 未 post-consume 时自动释放，防泄漏
RESERVE_TTL_SECONDS = 600
# 预估时给 completion 留的默认上限（无 max_tokens 时用）
DEFAULT_MAX_COMPLETION_TOKENS = 1024

_LUA_PATH = (
    Path(__file__).resolve().parents[1]
    / "infra"
    / "redis_scripts"
    / "preconsume.lua"
)
_PRECONSUME_LUA = _LUA_PATH.read_text(encoding="utf-8")


class PreConsumeAction(StrEnum):
    """预扣决策结果"""

    UNLIMITED = "unlimited"  # 无配额限制，无需预扣
    ZERO = "zero"  # 预估 0，无需预扣
    TRUSTED = "trusted"  # 额度充裕，信任跳过
    RESERVED = "reserved"  # 已在 Redis 预扣
    SQL_FALLBACK = "sql_fallback"  # Redis 不可达，SQL 串行化兜底（无持久预扣）


@dataclass(frozen=True, slots=True)
class PreConsumeResult:
    """预扣结果 —— post-consume 据 reserved/action 决定如何释放"""

    action: PreConsumeAction
    # 实际预扣的 token 数（仅 RESERVED 时 > 0；其余为 0）
    reserved: int


def reserved_key(workspace_id: int) -> str:
    return f"{_RESERVED_PREFIX}{workspace_id}"


def reserved_request_key(request_id: str) -> str:
    return f"{_RESERVED_REQ_PREFIX}{request_id}"


def estimate_request_tokens(
    prompt_tokens: int, max_completion_tokens: int
) -> int:
    """预估一次请求的 token 数（prompt + 预估 completion 上限）

    与 one-api 一致：宁可高估，post-consume 会按实际差额返还。
    """
    return max(0, prompt_tokens) + max(0, max_completion_tokens)


def estimate_text_tokens(
    text: str, *, max_completion_tokens: int = DEFAULT_MAX_COMPLETION_TOKENS
) -> int:
    """从 prompt 文本粗估请求 token 数（无 tokenizer 时的廉价启发式）

    经验值：英文 ~4 char/token，中文更密；用 //3 偏保守（略高估，安全）。
    """
    prompt_tokens = len(text) // 3 if text else 0
    return estimate_request_tokens(prompt_tokens, max_completion_tokens)


async def pre_consume(
    redis: Redis,
    session: AsyncSession,
    *,
    workspace_id: int | None,
    estimated_tokens: int,
    quota_remaining: int | None,
    request_id: str | None = None,
    trust_multiplier: int = DEFAULT_TRUST_MULTIPLIER,
) -> PreConsumeResult:
    """调用前预扣额度

    Args:
        redis: 异步 Redis 客户端
        session: DB session（Lua 不可达时 SQL 兜底用）
        workspace_id: 目标 workspace；None → 不限额（admin 视角）
        estimated_tokens: 预估 token 数（estimate_request_tokens 算）
        quota_remaining: 剩余额度 = limit - 已提交用量；None → 不限额
        request_id: 本次请求 id；传入则记单请求预扣标记，供 post_consume 精确释放
        trust_multiplier: 信任阈值倍数

    Returns:
        PreConsumeResult；RESERVED 时调用方须在 post 阶段 post_consume 释放。

    Raises:
        BusinessError(WorkspaceQuotaExceeded): 额度不足以覆盖本次预估。
    """
    if workspace_id is None or quota_remaining is None:
        return PreConsumeResult(PreConsumeAction.UNLIMITED, 0)
    if estimated_tokens <= 0:
        return PreConsumeResult(PreConsumeAction.ZERO, 0)
    if quota_remaining <= 0 or quota_remaining < estimated_tokens:
        raise BusinessError(
            ResultCode.WorkspaceQuotaExceeded,
            message=(
                f"workspace #{workspace_id} 配额不足：剩余 {quota_remaining}，"
                f"本次预估需 {estimated_tokens}"
            ),
        )
    # 信任阈值：额度远超预估 → 不预扣，省 Redis 往返
    if quota_remaining > trust_multiplier * estimated_tokens:
        return PreConsumeResult(PreConsumeAction.TRUSTED, 0)

    # 额度偏紧 → Redis 原子预扣
    try:
        newval = await redis.eval(
            _PRECONSUME_LUA,
            1,
            reserved_key(workspace_id),
            estimated_tokens,
            quota_remaining,
            RESERVE_TTL_SECONDS,
        )
    except RedisError:
        logger.warning(
            "pre_consume Redis 不可达，降级 SQL FOR UPDATE | ws={}", workspace_id
        )
        return await _pre_consume_sql_fallback(
            session, workspace_id=workspace_id, estimated_tokens=estimated_tokens
        )

    if int(newval) < 0:
        raise BusinessError(
            ResultCode.WorkspaceQuotaExceeded,
            message=(
                f"workspace #{workspace_id} 并发预扣超额：在途预扣 + 本次预估 "
                f"({estimated_tokens}) 超出剩余 {quota_remaining}"
            ),
        )
    # 记单请求预扣标记，供 post_consume 精确释放（best-effort）
    if request_id is not None:
        try:
            await redis.set(
                reserved_request_key(request_id),
                estimated_tokens,
                ex=RESERVE_TTL_SECONDS,
            )
        except RedisError:
            logger.warning(
                "pre_consume 记单请求标记失败（counter TTL 兜底）| rid={}",
                request_id,
            )
    return PreConsumeResult(PreConsumeAction.RESERVED, estimated_tokens)


async def post_consume(
    redis: Redis, *, workspace_id: int | None, request_id: str
) -> int:
    """调用后结算：释放本次请求的预扣（差额自然返还）

    pre_consume 预扣的是**预估**值；调用完成后实际用量由 quota_service.increment_usage
    原子落 SQL（committed 用量的最终真相）。这里只把预估预扣从在途计数里放掉 ——
    预估与实际的差额因此自动回到可用额度（不需要显式算 delta）。

    幂等 + best-effort：标记不存在（trusted/unlimited/已释放）→ 返回 0；Redis 不可达
    → warn 并返回 0（绝不抛错污染主路径，TTL 也会兜底释放）。

    Returns:
        实际释放的预扣 token 数（0 表示无预扣可放）。
    """
    if workspace_id is None:
        return 0
    req_key = reserved_request_key(request_id)
    try:
        raw = await redis.get(req_key)
        if raw is None:
            return 0
        amount = int(raw)
        await release_reservation(redis, workspace_id=workspace_id, amount=amount)
        await redis.delete(req_key)
        return amount
    except RedisError:
        logger.warning(
            "post_consume Redis 不可达（TTL 兜底）| ws={} | rid={}",
            workspace_id,
            request_id,
        )
        return 0


async def release_reservation(
    redis: Redis, *, workspace_id: int, amount: int
) -> None:
    """释放预扣（post-consume 调）—— DECRBY 回 reserved 计数

    best-effort：Redis 不可达只 warn（TTL 也会兜底释放），不抛错污染主路径。
    amount <= 0 直接跳过。
    """
    if amount <= 0:
        return
    try:
        remaining = await redis.decrby(reserved_key(workspace_id), amount)
        # 防御：浮点/异常导致负值时清零
        if int(remaining) < 0:
            await redis.set(reserved_key(workspace_id), 0)
    except RedisError:
        logger.warning(
            "release_reservation Redis 不可达（TTL 兜底）| ws={} | amount={}",
            workspace_id,
            amount,
        )


async def _pre_consume_sql_fallback(
    session: AsyncSession,
    *,
    workspace_id: int,
    estimated_tokens: int,
) -> PreConsumeResult:
    """Redis 不可达兜底：FOR UPDATE 锁行串行化，仅在 SQL 已耗尽时拒绝

    无持久预扣（Redis 才是预扣存储），但 FOR UPDATE 保证已提交用量视图一致，
    且绝不让请求 fail（红线）。
    """
    row = (
        await session.execute(
            select(WorkspaceQuota)
            .where(WorkspaceQuota.workspace_id == workspace_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None or row.token_quota_monthly is None:
        return PreConsumeResult(PreConsumeAction.SQL_FALLBACK, 0)
    if row.token_used_current_month >= row.token_quota_monthly:
        raise BusinessError(
            ResultCode.WorkspaceQuotaExceeded,
            message=(
                f"workspace #{workspace_id} 本月 token 配额已用尽 "
                f"({row.token_used_current_month}/{row.token_quota_monthly})"
            ),
        )
    return PreConsumeResult(PreConsumeAction.SQL_FALLBACK, 0)
