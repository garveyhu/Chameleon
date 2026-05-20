"""具名 getter —— 业务代码统一从这里取配置

不暴露 setter（运行时不可变）。改配置走编辑文件 + 重启。
"""

import os

from chameleon.core.config.base_settings import ConfigError
from chameleon.core.config.env_settings import env_settings
from chameleon.core.config.json_settings import (
    chameleon_settings,
    model_settings,
    url_settings,
)

# ── 模型相关 ─────────────────────────────────────────────


def case_llm() -> str | None:
    return model_settings.get("cases.llm")


def case_embedding() -> str | None:
    return model_settings.get("cases.embedding")


def case_vision() -> str | None:
    return model_settings.get("cases.vision")


def llm_model_config(name: str) -> dict:
    for m in model_settings.get("models.llm", []) or []:
        if m.get("name") == name:
            return m
    raise ConfigError(f"llm model not found in model.json: {name}")


def embedding_model_config(name: str) -> dict:
    for m in model_settings.get("models.embedding", []) or []:
        if m.get("name") == name:
            return m
    raise ConfigError(f"embedding model not found in model.json: {name}")


def llm_provider_credential(provider: str) -> tuple[str, str]:
    """返回 (base_url, api_key)。fail-fast。"""
    cfg = model_settings.get(f"providers.{provider}")
    if not cfg:
        raise ConfigError(f"provider not configured: {provider}")
    url_alias = cfg.get("url_alias")
    key_env = cfg.get("key_env")
    if not url_alias or not key_env:
        raise ConfigError(
            f"provider {provider} missing url_alias / key_env in model.json"
        )
    url = url_settings.get(url_alias)
    if not url:
        raise ConfigError(f"url alias not found in baseurl.json: {url_alias}")
    key = os.environ.get(key_env)
    if not key:
        raise ConfigError(f"env not set: {key_env}")
    return url, key


def embedding_dim() -> int:
    """v1 全局固定（与 chunks.embedding 列匹配）"""
    return chameleon_settings.get("knowledge.embedding_dim") or 1536


# ── 会话 ─────────────────────────────────────────────────


def session_history_limit() -> int:
    return chameleon_settings.get("session.history_limit") or 20


def session_title_max_length() -> int:
    return chameleon_settings.get("session.title_max_length") or 30


def session_ai_title_generation() -> bool:
    return bool(chameleon_settings.get("session.ai_title_generation"))


# ── 知识库 ───────────────────────────────────────────────


def kb_default_top_k() -> int:
    return chameleon_settings.get("knowledge.default_top_k") or 5


def kb_chunk_size() -> int:
    return chameleon_settings.get("knowledge.chunk_size") or 800


def kb_chunk_overlap() -> int:
    return chameleon_settings.get("knowledge.chunk_overlap") or 100


def kb_ingest_concurrency() -> int:
    return chameleon_settings.get("knowledge.ingest_concurrency") or 4


# ── 流式 ─────────────────────────────────────────────────


def stream_chunk_flush_ms() -> int:
    return chameleon_settings.get("stream.chunk_flush_ms") or 50


def stream_max_event_size_kb() -> int:
    return chameleon_settings.get("stream.max_event_size_kb") or 64


# ── Provider 超时 ────────────────────────────────────────


def provider_timeout_ms(provider: str) -> int:
    return (
        chameleon_settings.get(f"provider_timeout_ms.{provider}")
        or chameleon_settings.get("provider_timeout_ms.default")
        or 60000
    )


# ── 审计 ─────────────────────────────────────────────────


def call_log_retention_days() -> int | None:
    return chameleon_settings.get("call_log.retention_days")


# ── env 快捷 ────────────────────────────────────────────


def database_url() -> str:
    return env_settings.DATABASE_URL


def log_level() -> str:
    return env_settings.LOG_LEVEL


def chameleon_instance_id() -> int:
    return env_settings.CHAMELEON_INSTANCE_ID
