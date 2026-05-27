"""AppTemplate ORM —— P22.5 PR #83

业务：可一键克隆的模板（assistant / agent / workflow / rag）。

红线（plan §2 P22）：
- ⛔ 用户自传 template 默认 verified=False；不进默认推荐列表
- ⛔ install 时按 verified 校验
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
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, TimestampMixin, snowflake_pk


class AppTemplate(Base, TimestampMixin):
    """应用市场模板"""

    __tablename__ = "app_templates"

    id: Mapped[int] = snowflake_pk()
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: assistant / agent / workflow / rag
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    #: 完整 spec：graph + agents + KB 关联（JSONB；install 时按 category dispatch）
    spec_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    #: 封面图 URL（可选；MinIO presigned URL）
    cover_image: Mapped[str | None] = mapped_column(String(512), nullable=True)
    #: 是否官方审核（true 才进默认列表）
    verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: 下载次数（install 一次 +1）
    downloads: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_app_templates_verified_cat", "verified", "category"),
        Index("ix_app_templates_downloads", "downloads"),
    )
