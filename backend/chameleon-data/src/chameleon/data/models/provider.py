"""模型 / 平台 provider ORM

Provider 表存：
- LLM / embedding 服务商（qwen / deepseek / openai 等）
- 外部 agent 平台（dify / fastgpt 等）

api_key_encrypted 用 AES-256-GCM 加密（utils.crypto.encrypt），读出时按需 decrypt。
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.data.models.base import Base, SoftDeleteMixin, TimestampMixin
from chameleon.data.utils.snowflake import next_id


class Provider(Base, TimestampMixin, SoftDeleteMixin):
    """通用 provider 表

    kind 决定它能为谁用：
    - kind='llm' / 'embedding'        → LLMFactory / EmbeddingFactory 读
    - kind='dify' / 'fastgpt' / ...   → providers.<kind> 后端实例配置
    """

    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_providers_kind", "kind"),)
