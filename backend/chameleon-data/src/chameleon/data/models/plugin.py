"""PluginInstance ORM —— P19.2 PR #33

业务：admin 安装的插件实例（provider / tool / embedding）。
builtin 插件（local/dify/fastgpt）由首次启动 seed，source='builtin'，禁删。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.data.models.base import Base, snowflake_pk


class PluginInstance(Base):
    """已安装插件实例"""

    __tablename__ = "plugin_instances"

    id: Mapped[int] = snowflake_pk()
    plugin_key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # provider | tool | embedding
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    # builtin | local | git | pypi
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="local"
    )
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False)
    # 用户配置（敏感字段未来由 SDK 标记 sensitive → 加密存储）
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
