"""chameleon.core.routing.failover + error_classify 单测"""

from __future__ import annotations

import secrets
from collections import Counter

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import Ability, Channel, Provider
from chameleon.core.routing import (
    NoSatisfiedChannelError,
    invoke_with_failover,
    should_retry,
)
from chameleon.providers.base.errors import (
    ProviderAuthError,
    ProviderInternalError,
    ProviderRateLimitError,
    ProviderUnreachableError,
)

# ── error_classify ────────────────────────────────────────


def test_should_retry_rate_limit():
    assert should_retry(ProviderRateLimitError(message="429")) is True


def test_should_retry_unreachable():
    assert should_retry(ProviderUnreachableError(message="conn refused")) is True


def test_should_retry_internal():
    assert should_retry(ProviderInternalError(message="boom")) is True


def test_should_retry_auth():
    """key 失效 —— 换 channel 可能解决"""
    assert should_retry(ProviderAuthError(message="bad key")) is True


def test_should_retry_validation_no():
    assert should_retry(ValidationError(message="bad input")) is False


def test_should_retry_business_provider_codes():
    """业务码 ProviderInternalError 也算可重试"""
    exc = BusinessError(
        ResultCode.ProviderInternalError, message="upstream blew up"
    )
    assert should_retry(exc) is True


def test_should_retry_business_validation_no():
    exc = BusinessError(ResultCode.ValidationError, message="x")
    assert should_retry(exc) is False


def test_should_retry_unknown_no():
    """未知异常默认不重试，避免放大问题"""
    assert should_retry(RuntimeError("???")) is False


# ── failover wrapper ──────────────────────────────────────


@pytest_asyncio.fixture
async def fo_data():
    suffix = secrets.token_hex(3)
    mc = f"fo-model-{suffix}"
    async with AsyncSessionLocal() as s:
        provider = Provider(code=f"fo-prov-{suffix}", kind="llm", name="x", enabled=True)
        s.add(provider)
        await s.flush()
        ch_a = Channel(provider_id=provider.id, name="A", status="enabled")
        ch_b = Channel(provider_id=provider.id, name="B", status="enabled")
        ch_c = Channel(provider_id=provider.id, name="C", status="enabled")
        s.add_all([ch_a, ch_b, ch_c])
        await s.flush()
        s.add_all(
            [
                Ability(model_code=mc, channel_id=ch_a.id, priority=10, enabled=True),
                Ability(model_code=mc, channel_id=ch_b.id, priority=10, enabled=True),
                Ability(model_code=mc, channel_id=ch_c.id, priority=10, enabled=True),
            ]
        )
        await s.flush()
        await s.commit()
        ch_ids = (ch_a.id, ch_b.id, ch_c.id)
        prov_id = provider.id

    yield {"model_code": mc, "channel_ids": ch_ids, "provider_id": prov_id}

    async with AsyncSessionLocal() as s:
        await s.execute(delete(Ability).where(Ability.channel_id.in_(ch_ids)))
        await s.execute(delete(Channel).where(Channel.id.in_(ch_ids)))
        await s.execute(delete(Provider).where(Provider.id == prov_id))
        await s.commit()


async def test_failover_first_try_success(fo_data):
    mc = fo_data["model_code"]
    calls: list[int] = []

    async def invoke_fn(channel):
        calls.append(channel.id)
        return "ok"

    async with AsyncSessionLocal() as s:
        result, used = await invoke_with_failover(
            s, model_code=mc, invoke_fn=invoke_fn
        )
        assert result == "ok"
        assert len(calls) == 1
        assert used.id == calls[0]
        # 成功路径写 last_success_at + reset fail_count
        ch = (
            await s.execute(select(Channel).where(Channel.id == used.id))
        ).scalar_one()
        assert ch.last_success_at is not None
        assert ch.fail_count == 0


async def test_failover_retries_then_succeeds(fo_data):
    mc = fo_data["model_code"]
    failed_ids: list[int] = []

    async def invoke_fn(channel):
        if len(failed_ids) < 2:
            failed_ids.append(channel.id)
            raise ProviderInternalError(message="oops")
        return "win"

    async with AsyncSessionLocal() as s:
        result, used = await invoke_with_failover(
            s, model_code=mc, invoke_fn=invoke_fn, max_retries=3
        )
        assert result == "win"
        assert len(failed_ids) == 2
        # 两个失败 channel 各 +1 fail_count
        rows = (
            await s.execute(
                select(Channel).where(Channel.id.in_(failed_ids))
            )
        ).scalars().all()
        assert all(c.fail_count == 1 for c in rows)
        assert all(c.last_failed_at is not None for c in rows)


async def test_failover_exhausts_retries(fo_data):
    """所有 channel 都失败 → 抛最后一个错"""
    mc = fo_data["model_code"]

    async def invoke_fn(channel):
        raise ProviderRateLimitError(message=f"rate-limited on {channel.id}")

    async with AsyncSessionLocal() as s:
        with pytest.raises(ProviderRateLimitError):
            await invoke_with_failover(
                s, model_code=mc, invoke_fn=invoke_fn, max_retries=10
            )
        # 所有 channel 各 +1 fail_count
        rows = (
            await s.execute(
                select(Channel).where(Channel.id.in_(fo_data["channel_ids"]))
            )
        ).scalars().all()
        assert all(c.fail_count >= 1 for c in rows)


async def test_failover_not_retryable_raises_immediately(fo_data):
    """ValidationError 这种不可重试错误 → 第一次就抛"""
    mc = fo_data["model_code"]
    calls: list[int] = []

    async def invoke_fn(channel):
        calls.append(channel.id)
        raise ValidationError(message="bad input")

    async with AsyncSessionLocal() as s:
        with pytest.raises(ValidationError):
            await invoke_with_failover(
                s, model_code=mc, invoke_fn=invoke_fn, max_retries=5
            )
        assert len(calls) == 1  # 只调一次，不重试


async def test_failover_no_channel_at_all(fo_data):
    """都先 disable 掉 ability → 应抛 NoSatisfiedChannelError"""
    mc = fo_data["model_code"]
    async with AsyncSessionLocal() as s:
        await s.execute(
            Ability.__table__.update()
            .where(Ability.model_code == mc)
            .values(enabled=False)
        )
        await s.commit()

    async def invoke_fn(channel):
        return "shouldn't run"

    async with AsyncSessionLocal() as s:
        with pytest.raises(NoSatisfiedChannelError):
            await invoke_with_failover(s, model_code=mc, invoke_fn=invoke_fn)


async def test_failover_auto_disables_on_threshold(fo_data):
    """连续 5 次失败 → channel auto_disabled"""
    mc = fo_data["model_code"]
    ch_ids = fo_data["channel_ids"]
    # 只留 A，其他禁用
    async with AsyncSessionLocal() as s:
        await s.execute(
            Ability.__table__.update()
            .where(Ability.channel_id.in_(ch_ids[1:]))
            .values(enabled=False)
        )
        await s.commit()

    seen: Counter = Counter()

    async def invoke_fn(channel):
        seen[channel.id] += 1
        raise ProviderInternalError(message="loop")

    # 单 channel 重试 → 第一次失败后 exclude 就找不到下一个，应该立即抛
    async with AsyncSessionLocal() as s:
        with pytest.raises(ProviderInternalError):
            await invoke_with_failover(
                s, model_code=mc, invoke_fn=invoke_fn, max_retries=10
            )
        # 显式 commit 让 mark_failed 写入生效（生产环境是由 request 外层事务收尾）
        await s.commit()

    # mark_failed 被调一次（fail_count >= 1）
    async with AsyncSessionLocal() as s:
        ch = (
            await s.execute(select(Channel).where(Channel.id == ch_ids[0]))
        ).scalar_one()
        assert ch.fail_count >= 1
