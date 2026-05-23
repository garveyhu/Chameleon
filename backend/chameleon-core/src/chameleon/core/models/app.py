"""应用域 ORM：App + AppAgent

App 是业务方"应用"的抽象（一组 API key + 元数据 + 配额 + 授权的 agent 列表）。
app_key 是 slug 形态对外标识（业务方 API 调用时不再用），id 是 BigInt FK 给其他表引用。

AppAgent 是 app ↔ agent 多对多授权连接表：仅授权过的 agent 才允许这个 app 调。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, SoftDeleteMixin, TimestampMixin
from chameleon.core.models.workspace import WorkspaceScopedMixin
from chameleon.core.utils.snowflake import next_id


class App(Base, TimestampMixin, SoftDeleteMixin, WorkspaceScopedMixin):
    """业务方应用

    一个 app 关联 N 个 api_keys（同应用多 key：生产 / 测试 / 临时）。
    app_key（slug）对外可见、可改但谨慎；id（BigInt）内部 FK 用。
    """

    __tablename__ = "apps"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    # app_key 完整 unique（不软删过滤）—— 让其他表的 app_id FK 能引用
    # 软删时更名为 "__deleted_<id>_<original>" 释放原 app_key
    app_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active"
    )  # active / suspended
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    qpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qpd_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (Index("ix_apps_owner", "owner_user_id"),)


class AppAgent(Base):
    """app ↔ agent 多对多授权连接表

    业务调 invoke 前：校验 app 已授权该 agent，否则拒。
    """

    __tablename__ = "app_agents"

    app_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("apps.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    granted_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("app_id", "agent_id", name="pk_app_agents"),
    )
