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

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.components.llms.base import BaseLLM
from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import LLMModel, Provider
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
            defaults = model.defaults or {}
            instance = BaseLLM(
                model=model.code,
                api_key=api_key,
                api_base=provider.base_url or "",
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
