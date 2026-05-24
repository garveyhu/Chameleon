"""LLMFactory —— 从 DB providers + models 表构造 BaseLLM 实例

v0.2 改造（DB-driven）：
- 启动期 `await reload_llm_cache()` 一次性 load 所有 enabled 模型到内存
- 业务调用 `LLMFactory.create(name)` 同步从 cache 取（不阻塞事件循环）
- admin 改 model / provider 后调 `reload_llm_cache()` 让新配置生效

cache miss 不再 lazy load DB（避免业务路径上偷偷起异步 DB 调用）；
admin 改完配置必须显式调失效；启动 / 重启总是 reload 全量。
"""

from __future__ import annotations

import threading

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.components.llms.base import BaseLLM
from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import Channel, LLMModel, Provider
from chameleon.core.utils.crypto import get_or_decrypt

# 进程内 cache（启动期一次性 load）
_CACHE: dict[str, BaseLLM] = {}
_DEFAULT_NAME: str | None = None
_LOCK = threading.RLock()

# 测试桩
_OVERRIDE: BaseLLM | None = None


def set_for_test(client: BaseLLM | None) -> None:
    """测试用：注入桩；传 None 恢复正常路径"""
    global _OVERRIDE
    _OVERRIDE = client


# ── 启动期 async load ─────────────────────────────────────


def _channel_key(ch: Channel) -> str | None:
    """取 channel 的明文 key：优先单 key（api_key_encrypted），否则多 key 池首个。

    cache 静态构建只取一个 key；按请求轮转 / failover 需走 core.routing
    （resolve_channel + key_pool + invoke_with_failover），属后续重构。
    """
    if ch.api_key_encrypted:
        return get_or_decrypt(ch.api_key_encrypted)
    if ch.keys:
        return get_or_decrypt(ch.keys[0])
    return None


async def reload_llm_cache(default_name: str | None = None) -> int:
    """从 DB 全量重 load LLM 实例 cache

    Args:
        default_name: 没指定 name 时 LLMFactory.create() 用的默认模型名

    Returns:
        cache 中的模型数量
    """
    global _DEFAULT_NAME

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(LLMModel, Provider)
                .join(Provider, LLMModel.provider_id == Provider.id)
                .where(
                    LLMModel.kind == "chat",
                    LLMModel.enabled.is_(True),
                    LLMModel.deleted_at.is_(None),
                    Provider.enabled.is_(True),
                    Provider.deleted_at.is_(None),
                )
            )
        ).all()
        # 凭证按设计走 channels（provider.api_key_encrypted 仅兼容兜底）。
        # 每 provider 取优先级最高的 enabled channel；priority 同则取后建的。
        channels = (
            (
                await session.execute(
                    select(Channel)
                    .where(
                        Channel.status == "enabled",
                        Channel.deleted_at.is_(None),
                    )
                    .order_by(Channel.priority.desc(), Channel.id.desc())
                )
            )
            .scalars()
            .all()
        )

    channel_by_provider: dict[int, Channel] = {}
    for ch in channels:
        channel_by_provider.setdefault(ch.provider_id, ch)

    new_cache: dict[str, BaseLLM] = {}
    for model, provider in rows:
        try:
            ch = channel_by_provider.get(provider.id)
            ch_key = _channel_key(ch) if ch is not None else None
            # 凭证优先级：channel key > provider key（兼容期兜底）
            api_key = ch_key or get_or_decrypt(provider.api_key_encrypted) or ""
            api_base = (
                ch.base_url if ch is not None and ch.base_url else provider.base_url
            ) or ""
            defaults = model.defaults or {}
            instance = BaseLLM(
                model=model.code,
                api_key=api_key,
                api_base=api_base,
                temperature=defaults.get("temperature", 0.7),
                max_tokens=defaults.get("max_tokens"),
            )
            new_cache[model.code] = instance
        except Exception as e:
            logger.warning(
                "LLM cache: skip {} (provider {}): {}", model.code, provider.code, e
            )

    with _LOCK:
        _CACHE.clear()
        _CACHE.update(new_cache)
        if default_name:
            _DEFAULT_NAME = default_name
        elif _DEFAULT_NAME is None and new_cache:
            # 没显式指定 → 用 inventory.case_llm() 的值（dev 友好）
            from chameleon.core.config import inventory

            _DEFAULT_NAME = inventory.case_llm() or next(iter(new_cache), None)

    logger.info(
        "LLM cache reloaded: {} models, default={}", len(new_cache), _DEFAULT_NAME
    )
    return len(new_cache)


def invalidate_llm(name: str) -> None:
    """单条失效（admin 删除 model 时调；下次需要先 reload_llm_cache）"""
    with _LOCK:
        _CACHE.pop(name, None)


# ── 同步获取（业务热路径） ────────────────────────────────


class LLMFactory:
    @classmethod
    def create(cls, name: str | None = None) -> BaseLLM:
        if _OVERRIDE is not None:
            return _OVERRIDE

        with _LOCK:
            target = name or _DEFAULT_NAME
            if not target:
                raise BusinessError(
                    ResultCode.RegistryError,
                    message="未配置默认 LLM 模型 —— 启动期 reload_llm_cache 没找到任何 enabled chat model",
                )
            cached = _CACHE.get(target)
        if cached is None:
            raise BusinessError(
                ResultCode.RegistryError,
                message=f"LLM model 不存在或未启用：{target}",
            )
        return cached


# ── 顶层快捷函数（仿 sage components/inventory.py 模式） ──


def llm(name: str | None = None) -> BaseLLM:
    """获取 LLM 实例（默认走 cases.llm；可指定模型名）"""
    return LLMFactory.create(name)


def llm_by_name(name: str) -> BaseLLM:
    return LLMFactory.create(name)


async def resolve_llm(
    model_code: str | None = None,
    *,
    session: AsyncSession | None = None,
    group_id: int | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> BaseLLM:
    """按 model_code 经 channel 路由（Ability 路由 + C7 多 key 轮转）构建 per-request
    LLM 实例 —— 让 channels 的多 key 池 / 优先级真正作用于 LLM 调用（#30）。

    session 可选：调用方已有 session 就传入复用；否则本函数开一个短 session 仅做
    channel 解析（图节点 / retrieval 等无 session 的异步调用方用）。

    无 Ability / 可用 channel / channel 没配 key / 路由出错时，回退静态 cache
    （LLMFactory.create，即 #25 行为），保证不回归。failover（失败切下一 channel）
    对流式 LLM 较复杂，暂留给后续；本函数只做"选 channel + 选 key + 建实例"。
    """
    if _OVERRIDE is not None:
        return _OVERRIDE
    target = model_code or _DEFAULT_NAME
    if not target:
        return LLMFactory.create(None)  # 触发统一的"未配置默认 LLM"错误
    if session is not None:
        return await _resolve_llm_via_channel(
            session, target, group_id, temperature, max_tokens
        )
    async with AsyncSessionLocal() as s:
        return await _resolve_llm_via_channel(
            s, target, group_id, temperature, max_tokens
        )


async def _resolve_llm_via_channel(
    session: AsyncSession,
    target: str,
    group_id: int | None,
    temperature: float,
    max_tokens: int | None,
) -> BaseLLM:
    try:
        from chameleon.core.infra.redis import get_redis
        from chameleon.core.routing import (
            NoSatisfiedChannelError,
            build_channel_override,
            resolve_channel,
        )

        try:
            channel = await resolve_channel(
                session, model_code=target, group_id=group_id
            )
        except NoSatisfiedChannelError:
            return LLMFactory.create(target)  # 无 Ability/channel → 回退 cache

        ov = await build_channel_override(get_redis(), channel)
        api_key = ov.get("api_key") or ""
        if not api_key:
            return LLMFactory.create(target)  # channel 没配 key → 回退
        base_url = ov.get("base_url")
        if not base_url:
            prov = (
                await session.execute(
                    select(Provider).where(Provider.id == channel.provider_id)
                )
            ).scalar_one_or_none()
            base_url = (prov.base_url if prov else None) or ""
        logger.debug(
            "resolve_llm via channel | model={} | channel_id={}", target, channel.id
        )
        return BaseLLM(
            model=target,
            api_key=api_key,
            api_base=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception:
        logger.exception("resolve_llm channel routing failed, fallback to cache")
        return LLMFactory.create(target)
