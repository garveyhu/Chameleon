"""EmbeddingClient 工厂 —— DB-driven（与 LLMFactory 同口径）

v0.3 改造：从 model_def 表（kind='embedding'）构造 OpenAICompatEmbedding，
对齐对话型 reload_llm_cache：
- 启动期 `await reload_embedding_cache()` 一次性 load 所有 enabled embedding 到内存
- 业务调用 `get_embedding_client(name)` 同步从 cache 取（不阻塞事件循环）
- admin 改 model / provider 后调 `reload_embedding_cache()` 让新配置生效

凭证 / 上游名解析与 reload_llm_cache 完全一致：newapi 模式且有 enabled gateway
provider → 统一走网关（model 名用 upstream_name or code）；否则走模型自身 provider。
dim / batch_size 从 DB 取（dim=列，batch_size=defaults.batch_size），让配置抽屉真正生效。
"""

from __future__ import annotations

import threading

from loguru import logger
from sqlalchemy import select

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.config import inventory
from chameleon.core.embedding.base import EmbeddingClient
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import LLMModel, Provider
from chameleon.data.utils.crypto import get_or_decrypt
from chameleon.integrations.embedding.openai_compat import OpenAICompatEmbedding

# 进程内 cache（启动期一次性 load，按 model code 缓存）
_CACHE: dict[str, EmbeddingClient] = {}
_DEFAULT_NAME: str | None = None
_LOCK = threading.RLock()
_OVERRIDE: EmbeddingClient | None = None  # 测试用


def set_for_test(client: EmbeddingClient | None) -> None:
    """测试用：注入 mock；传 None 恢复默认"""
    global _OVERRIDE
    _OVERRIDE = client


async def reload_embedding_cache(default_name: str | None = None) -> int:
    """从 DB 全量重 load embedding 实例 cache（镜像 reload_llm_cache）。

    Returns:
        cache 中的 embedding 模型数量
    """
    global _DEFAULT_NAME

    mode = inventory.gateway_mode()
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(LLMModel, Provider)
                .join(Provider, LLMModel.provider_id == Provider.id)
                .where(
                    LLMModel.kind == "embedding",
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
                    "embedding 本次回退各模型直连",
                    gw_code,
                )

    new_cache: dict[str, EmbeddingClient] = {}
    for model, provider in rows:
        try:
            if not model.dim:
                logger.warning("embedding cache: skip {} (无 dim)", model.code)
                continue
            eff = gateway if gateway is not None else provider
            api_key = get_or_decrypt(eff.api_key_encrypted) or ""
            api_base = eff.base_url or ""
            defaults = model.defaults or {}
            batch_size = defaults.get("batch_size")
            client = OpenAICompatEmbedding(
                base_url=api_base,
                api_key=api_key,
                # 走网关时用 upstream_name（new-api 认的名）；直连用 code
                model=(model.upstream_name or model.code)
                if eff.kind == "gateway"
                else model.code,
                model_code=model.code,
                dim=int(model.dim),
                **({"batch_size": int(batch_size)} if batch_size else {}),
            )
            new_cache[model.code] = client
        except Exception as e:
            logger.warning(
                "embedding cache: skip {} (provider {}): {}",
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
            _DEFAULT_NAME = inventory.case_embedding() or next(iter(new_cache), None)

    logger.info(
        "embedding cache reloaded: {} models, default={}",
        len(new_cache),
        _DEFAULT_NAME,
    )
    return len(new_cache)


def invalidate_embedding(name: str) -> None:
    """单条失效（admin 删除 model 时调；下次需要先 reload_embedding_cache）"""
    with _LOCK:
        _CACHE.pop(name, None)


def get_embedding_client(model: str | None = None) -> EmbeddingClient:
    """取 embedding 客户端（同步，从启动期 cache 取）。

    model=None → 用 _DEFAULT_NAME（默认 inventory.case_embedding()）。
    cache miss 不 lazy load DB（与 LLMFactory 一致，避免业务热路径偷起异步 DB）。
    """
    if _OVERRIDE is not None:
        return _OVERRIDE

    with _LOCK:
        target = model or _DEFAULT_NAME or inventory.case_embedding()
        if not target:
            raise BusinessError(
                ResultCode.RegistryError,
                message="未配置默认 embedding 模型 —— 启动期 reload_embedding_cache "
                "没找到任何 enabled embedding model",
            )
        cached = _CACHE.get(target)
    if cached is None:
        raise BusinessError(
            ResultCode.RegistryError,
            message=f"embedding model 不存在或未启用：{target}",
        )
    return cached
