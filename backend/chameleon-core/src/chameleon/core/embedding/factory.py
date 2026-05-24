"""EmbeddingClient 工厂

读 inventory.case_embedding() + inventory.embedding_model_config(name) + provider 凭据
单例缓存（按 model name 缓存）。
"""

from __future__ import annotations

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.config import inventory
from chameleon.core.embedding.base import EmbeddingClient
from chameleon.core.embedding.openai_compat import OpenAICompatEmbedding

_CACHE: dict[str, EmbeddingClient] = {}
_OVERRIDE: EmbeddingClient | None = None  # 测试用


def set_for_test(client: EmbeddingClient | None) -> None:
    """测试用：注入 mock；传 None 恢复默认"""
    global _OVERRIDE
    _OVERRIDE = client


def get_embedding_client(model: str | None = None) -> EmbeddingClient:
    """取 embedding 客户端

    model=None → 用 inventory.case_embedding() 的默认
    """
    if _OVERRIDE is not None:
        return _OVERRIDE

    name = model or inventory.case_embedding()
    if not name:
        raise BusinessError(
            ResultCode.RegistryError,
            message="no default embedding model configured (model.json cases.embedding)",
        )

    cached = _CACHE.get(name)
    if cached is not None:
        return cached

    cfg = inventory.embedding_model_config(name)
    provider = cfg.get("provider")
    dim = cfg.get("dim")
    if not provider or not dim:
        raise BusinessError(
            ResultCode.RegistryError,
            message=f"embedding model {name} missing provider / dim in model.json",
        )

    base_url, api_key = inventory.llm_provider_credential(provider)
    client = OpenAICompatEmbedding(
        base_url=base_url,
        api_key=api_key,
        model=name,
        dim=int(dim),
    )
    _CACHE[name] = client
    return client
