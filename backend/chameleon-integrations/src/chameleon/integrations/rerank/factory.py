"""Reranker 工厂 —— DB-driven（与 embedding/llm 同口径）

启动期 `await reload_rerank_cache()` 一次性 load 所有 enabled rerank 模型到内存；
业务/engine 经 `get_reranker(name)` 同步从 cache 取；admin 改 model/provider 后重载。

凭证/上游名解析与 reload_llm_cache 一致：newapi 模式且有 enabled gateway provider →
走网关（model 名用 upstream_name or code）；否则走模型自身 provider。
"""

from __future__ import annotations

import threading

from loguru import logger
from sqlalchemy import select

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.config import inventory
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import LLMModel, Provider
from chameleon.data.utils.crypto import get_or_decrypt
from chameleon.integrations.rerank.openai_compat import OpenAICompatReranker

_CACHE: dict[str, OpenAICompatReranker] = {}
_DEFAULT_NAME: str | None = None
_LOCK = threading.RLock()
_OVERRIDE: OpenAICompatReranker | None = None  # 测试用


def set_for_test(client: OpenAICompatReranker | None) -> None:
    """测试用：注入 mock；传 None 恢复默认"""
    global _OVERRIDE
    _OVERRIDE = client


async def reload_rerank_cache(default_name: str | None = None) -> int:
    """从 DB 全量重 load rerank 实例 cache（镜像 reload_embedding_cache）。"""
    global _DEFAULT_NAME

    mode = inventory.gateway_mode()
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(LLMModel, Provider)
                .join(Provider, LLMModel.provider_id == Provider.id)
                .where(
                    LLMModel.kind == "rerank",
                    LLMModel.enabled.is_(True),
                    LLMModel.deleted_at.is_(None),
                    Provider.enabled.is_(True),
                    Provider.deleted_at.is_(None),
                )
            )
        ).all()

        gateway: Provider | None = None
        if mode == "newapi":
            gw_code = inventory.gateway_provider_code()
            gateway = (
                await session.execute(
                    select(Provider).where(
                        Provider.code == gw_code,
                        Provider.enabled.is_(True),
                        Provider.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if gateway is None:
                logger.warning(
                    "gateway.mode=newapi 但找不到 enabled gateway provider '{}'，"
                    "rerank 本次回退各模型直连",
                    gw_code,
                )

    new_cache: dict[str, OpenAICompatReranker] = {}
    for model, provider in rows:
        try:
            eff = gateway if gateway is not None else provider
            client = OpenAICompatReranker(
                base_url=eff.base_url or "",
                api_key=get_or_decrypt(eff.api_key_encrypted) or "",
                model=(model.upstream_name or model.code)
                if eff.kind == "gateway"
                else model.code,
                model_code=model.code,
            )
            new_cache[model.code] = client
        except Exception as e:
            logger.warning(
                "rerank cache: skip {} (provider {}): {}",
                model.code,
                provider.code,
                e,
            )

    with _LOCK:
        _CACHE.clear()
        _CACHE.update(new_cache)
        if default_name:
            _DEFAULT_NAME = default_name
        elif _DEFAULT_NAME is None and new_cache:
            _DEFAULT_NAME = next(iter(new_cache), None)

    logger.info(
        "rerank cache reloaded: {} models, default={}", len(new_cache), _DEFAULT_NAME
    )
    return len(new_cache)


def invalidate_rerank(name: str) -> None:
    """单条失效（admin 删除 model 时调）"""
    with _LOCK:
        _CACHE.pop(name, None)


def get_reranker(name: str | None = None) -> OpenAICompatReranker:
    """取 rerank 客户端（同步，从启动期 cache 取）。

    name=None → 用 _DEFAULT_NAME（首个已启用 rerank 模型 / 由默认设置指定）。
    cache miss 不 lazy load DB（与 llm/embedding 一致）。
    """
    if _OVERRIDE is not None:
        return _OVERRIDE

    with _LOCK:
        target = name or _DEFAULT_NAME
        if not target:
            raise BusinessError(
                ResultCode.RegistryError,
                message="未配置 rerank 模型 —— 启动期 reload_rerank_cache "
                "没找到任何 enabled rerank model",
            )
        cached = _CACHE.get(target)
    if cached is None:
        raise BusinessError(
            ResultCode.RegistryError,
            message=f"rerank model 不存在或未启用：{target}",
        )
    return cached
