"""模型定义 ORM（LLM / embedding）

类名 Model 与 SQLAlchemy DSL 中的 model 概念易混 —— 文件名取 model_def.py。
对外 import 时建议：`from chameleon.data.models import LLMModel` （__init__ 里 alias）。
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.data.models.base import Base, SoftDeleteMixin, TimestampMixin
from chameleon.data.utils.snowflake import next_id


class LLMModel(Base, TimestampMixin, SoftDeleteMixin):
    """LLM 或 embedding 模型定义

    LLMFactory / EmbeddingFactory 启动时从 providers 表 + models 表组装客户端。
    """

    __tablename__ = "models"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    provider_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # chat / embedding
    dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    defaults: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("uq_models_provider_code", "provider_id", "code", unique=True),
        Index("ix_models_kind", "kind"),
    )
