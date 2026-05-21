"""嵌入式智能体配置 ORM

业务方网页通过 `<script data-embed-key="emb_xxx">` 引入，chameleon 据 embed_key 加载本配置。
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, SoftDeleteMixin, TimestampMixin
from chameleon.core.utils.snowflake import next_id


class EmbedConfig(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "embed_configs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    embed_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False
    )
    app_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("apps.id", ondelete="RESTRICT"), nullable=False
    )
    allowed_origins: Mapped[list | None] = mapped_column(JSON, nullable=True)
    ui_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    behavior: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (
        Index("ix_embed_configs_agent", "agent_id"),
        Index("ix_embed_configs_app", "app_id"),
    )
