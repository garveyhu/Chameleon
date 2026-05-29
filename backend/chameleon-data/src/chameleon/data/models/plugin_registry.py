"""PluginRegistryEntry ORM —— P20.2 PR #48

业务：admin 配置的远端 Plugin Registry（marketplace）。

注意区分两个 PluginRegistry：
- `chameleon.core.plugins.registry.PluginRegistry`：进程内单例，管已安装插件
- `chameleon.data.models.plugin_registry.PluginRegistryEntry`：DB 行，
  存远端 marketplace 的 URL + 凭据 + 同步时间戳
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.data.models.base import Base, TimestampMixin, snowflake_pk


class PluginRegistryEntry(Base, TimestampMixin):
    """已配置的远端 plugin marketplace"""

    __tablename__ = "plugin_registries"

    id: Mapped[int] = snowflake_pk()
    registry_url: Mapped[str] = mapped_column(
        String(256), nullable=False, unique=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # publishers pinning：缓存的 index.publishers map（admin 信任的发布者列表）
    pubkey_pinning: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 同步缓存的 plugin entries（避免每次浏览都打远端）
    cached_entries: Mapped[list | None] = mapped_column(JSON, nullable=True)
