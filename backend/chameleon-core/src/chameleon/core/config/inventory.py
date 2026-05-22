"""具名 getter —— 业务代码统一从这里取配置

不暴露 setter（运行时不可变）。改配置走编辑文件 + 重启。

sage 风格分层：
- AI 相关 → model_settings（含 provider api_key + base_url）
- 中间件 → component_settings（DB / Redis）
- 业务参数 → chameleon_settings
- 部署级 override → env_settings
- 外部 agent URL → url_settings
"""

from chameleon.core.config.base_settings import ConfigError
from chameleon.core.config.env_settings import env_settings
from chameleon.core.config.json_settings import (
    chameleon_settings,
    component_settings,
    model_settings,
    url_settings,
)

# ── 模型相关（全从 model.json） ─────────────────────────


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
    """返回 (base_url, api_key) —— 全部从 model.json 取（sage 风格）"""
    cfg = model_settings.get(f"providers.{provider}")
    if not cfg:
        raise ConfigError(f"provider not configured in model.json: {provider}")

    base_url = cfg.get("base_url")
    api_key = cfg.get("api_key")
    if not base_url:
        raise ConfigError(f"providers.{provider}.base_url 缺失（model.json）")
    if not api_key:
        raise ConfigError(
            f"providers.{provider}.api_key 缺失（model.json）—— "
            "请把 API key 填进 config/model.json"
        )
    return base_url, api_key


def embedding_dim() -> int:
    """v1 全局固定（与 chunks.embedding 列匹配）"""
    return chameleon_settings.get("knowledge.embedding_dim") or 1536


# ── 中间件（DB / Redis 等，从 component.json） ─────────


def database_url() -> str:
    """组装数据库 URL

    优先级（高→低）：
    1. env DATABASE_URL（容器化部署 override）
    2. component.json database.* 字段拼接
    """
    override = env_settings.DATABASE_URL
    if override:
        return override

    db = component_settings.get("database") or {}
    if not db:
        raise ConfigError("component.json database.* 未配置且无 DATABASE_URL env")

    # SQLAlchemy dialect 名映射（sage 习惯用 "postgres" 简写）
    db_type_raw = db.get("type", "postgresql")
    db_type = {"postgres": "postgresql", "mysql": "mysql", "sqlite": "sqlite"}.get(
        db_type_raw, db_type_raw
    )
    driver = db.get("driver", "asyncpg")
    user = db.get("user", "")
    pwd = db.get("password", "")
    host = db.get("host", "localhost")
    port = db.get("port", 5432)
    name = db.get("db", "")

    auth = f"{user}:{pwd}@" if user else ""
    return f"{db_type}+{driver}://{auth}{host}:{port}/{name}"


def redis_config() -> dict:
    """Redis 连接信息（env > component.json）

    容器化部署：把连接信息放 env 即可，无需挂载 component.json
    """
    base = dict(component_settings.get("redis") or {})
    if env_settings.REDIS_HOST is not None:
        base["host"] = env_settings.REDIS_HOST
    if env_settings.REDIS_PORT is not None:
        base["port"] = env_settings.REDIS_PORT
    if env_settings.REDIS_DB is not None:
        base["db"] = env_settings.REDIS_DB
    if env_settings.REDIS_PASSWORD is not None:
        base["password"] = env_settings.REDIS_PASSWORD
    return base


def minio_config() -> dict:
    """MinIO 连接信息（env > component.json）

    字段：endpoint / secure / bucket / public_url / access_key / secret_key
    """
    base = dict(component_settings.get("minio") or {})
    if env_settings.MINIO_ENDPOINT is not None:
        base["endpoint"] = env_settings.MINIO_ENDPOINT
    if env_settings.MINIO_BUCKET is not None:
        base["bucket"] = env_settings.MINIO_BUCKET
    # 凭据只走 env（不进 component.json）
    base["access_key"] = env_settings.MINIO_ACCESS_KEY or ""
    base["secret_key"] = env_settings.MINIO_SECRET_KEY or ""
    base.setdefault("endpoint", "127.0.0.1:9000")
    base.setdefault("secure", False)
    base.setdefault("bucket", "chameleon")
    base.setdefault(
        "public_url",
        f"{'https' if base['secure'] else 'http'}://{base['endpoint']}",
    )
    return base


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


# ── 全局 ────────────────────────────────────────────────


def log_level() -> str:
    """日志级别：env override 优先，否则 chameleon.json，最后默认 INFO"""
    return env_settings.LOG_LEVEL or chameleon_settings.get("log_level") or "INFO"


def chameleon_instance_id() -> int:
    return env_settings.CHAMELEON_INSTANCE_ID


# ── 外部 agent 平台 URL（baseurl.json） ────────────────


def external_platform_url(alias: str) -> str | None:
    """如 `dify-default` / `fastgpt-default` —— agents.yaml `${baseurl:x}` 占位符引用"""
    return url_settings.get(alias)
