"""LLMFactory —— 从 DB providers + models 表构造 BaseLLM 实例

v0.2 改造（DB-driven）：
- 启动期 `await reload_llm_cache()` 一次性 load 所有 enabled 模型到内存
- 业务调用 `LLMFactory.create(name)` 同步从 cache 取（不阻塞事件循环）
- admin 改 model / provider 后调 `reload_llm_cache()` 让新配置生效

cache miss 不再 lazy load DB（避免业务路径上偷偷起异步 DB 调用）；
admin 改完配置必须显式调失效；启动 / 重启总是 reload 全量。

凭证来源：provider.api_key_encrypted / provider.base_url —— 直连上游
（如把 oneapi 之类网关作为一个 provider 接入），不再经内部模型网关路由。
"""

from __future__ import annotations

import threading

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.components.llms.base import BaseLLM
from chameleon.core.observe.llm_recorder import GenerationRecorder
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import LLMModel, Provider
from chameleon.data.utils.crypto import get_or_decrypt

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

    new_cache: dict[str, BaseLLM] = {}
    for model, provider in rows:
        try:
            api_key = get_or_decrypt(provider.api_key_encrypted) or ""
            api_base = provider.base_url or ""
            defaults = model.defaults or {}
            # S6：每个 cache 实例烧进 GenerationRecorder —— 任何路径
            # 拿到这个实例调 .ainvoke()/.astream() 都会自动记一条 generation
            # call_log（归属字段从 TraceContext / ContextVar 读，无 scope 兜底）
            instance = BaseLLM(
                model=model.code,
                api_key=api_key,
                api_base=api_base,
                temperature=defaults.get("temperature", 0.7),
                max_tokens=defaults.get("max_tokens"),
                callbacks=[GenerationRecorder(model_code=model.code)],
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
    """按 model_code 取 LLM 实例（直连 provider）。

    历史上这里做过内部 channel 路由（已随模型网关移除）；现在直接走启动期
    cache。`session` / `group_id` / `temperature` / `max_tokens` 仅为兼容旧
    调用签名保留，不再生效（实例用模型自身 defaults）。
    """
    return LLMFactory.create(model_code)
