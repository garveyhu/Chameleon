"""ToolInstance ORM —— P18.2 admin 配的工具实例

业务：内置 Tool 类一律存代码层（chameleon.integrations.tools.builtins/*）；
本表只存 admin 给某 tool_key 配的运行时参数（如 HTTPTool 的 allowed_url_prefixes）
+ 启用开关。

唯一约束：tool_key —— 同一个内置 tool 只配一次实例（v0.4 简化）。
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.data.models.base import Base, TimestampMixin, snowflake_pk


class ToolInstance(Base, TimestampMixin):
    """admin 配的 tool 运行时实例（一个 tool_key 一条记录）"""

    __tablename__ = "tool_instances"

    id: Mapped[int] = snowflake_pk()
    tool_key: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 运行时 config（透传给 Tool(config) 构造器）
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
