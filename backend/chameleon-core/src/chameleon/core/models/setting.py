"""系统配置 ORM —— key/value 风格的运行时可改配置

业务参数（QPM 默认 / KB chunk 默认 / 会话历史长度等）目前在 config/chameleon.json，
设置入此表后，admin UI 能改、改完缓存失效、不重启生效。

scope 字段区分配置归属：
- 'global'    系统级（管理员）
- 'app:<id>'  特定 app 私有（业务方覆盖默认值）
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, TimestampMixin
from chameleon.core.utils.snowflake import next_id


class Setting(Base, TimestampMixin):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, default="global")
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    value_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="json"
    )  # json / string / int / bool
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("uq_settings_scope_key", "scope", "key", unique=True),
    )
