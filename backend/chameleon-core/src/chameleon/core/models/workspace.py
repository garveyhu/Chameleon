"""Workspace / Team / Membership / Quota ORM —— P19.3 PR #36

业务概念：
- Workspace：租户隔离边界；admin 切换 workspace 看到不同的 agents/kbs/graphs 等
- Team：workspace 下的子分组（仅元数据，权限不直接挂 team）
- Membership：user × workspace × (team) → role；admin 可看全部 workspace
- WorkspaceQuota：workspace 维度的 token / 请求配额（PR #39 兜底）

红线（plan §2 新增）：
- ⛔ 全部业务表 workspace_id NULLABLE + default=1 —— 老数据零迁移升级
- ⛔ default workspace (id=1) 由 alembic upgrade 幂等 seed；禁止删除
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    snowflake_pk,
)

DEFAULT_WORKSPACE_ID = 1


class WorkspaceScopedMixin:
    """业务表通用：归属哪个 workspace（NULLABLE，老数据 default=1）

    红线：不强制 NOT NULL 以保兼容老 API；service 层入参缺省走 current_app.workspace_id。
    """

    workspace_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class Workspace(Base, TimestampMixin, SoftDeleteMixin):
    """租户隔离边界"""

    __tablename__ = "workspaces"

    id: Mapped[int] = snowflake_pk()
    workspace_key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # free | pro | enterprise（PR #39 配额用）
    plan: Mapped[str] = mapped_column(
        String(16), nullable=False, default="free"
    )
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Team(Base, TimestampMixin):
    """workspace 下的子分组"""

    __tablename__ = "teams"

    id: Mapped[int] = snowflake_pk()
    workspace_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)


class Membership(Base):
    """user × workspace × (team) → role"""

    __tablename__ = "memberships"

    id: Mapped[int] = snowflake_pk()
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
    )
    # owner | admin | member | viewer
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "workspace_id",
            "team_id",
            name="uq_memberships_user_ws_team",
        ),
        Index("ix_memberships_user", "user_id"),
        Index("ix_memberships_workspace", "workspace_id"),
    )


class WorkspaceQuota(Base):
    """workspace 配额状态（PR #39 enforce 用）"""

    __tablename__ = "workspace_quotas"

    workspace_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # NULL = unlimited
    token_quota_monthly: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    token_used_current_month: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    request_quota_daily: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    request_used_today: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    reset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
