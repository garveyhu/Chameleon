"""鉴权域 ORM：User / Role / Permission + 两张连接表

按 redesign.md §3.1 ER：
  users ─< user_roles >─ roles ─< role_permissions >─ permissions

权限点命名约定：<resource>:<action>，action ∈ {read, write, delete, manage}。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chameleon.core.models.base import Base, SoftDeleteMixin, TimestampMixin
from chameleon.core.utils.snowflake import next_id


class User(Base, TimestampMixin, SoftDeleteMixin):
    """管理面板用户

    密码以 argon2id 哈希存储（utils.passwords）。
    password_version：改密时 +1，让所有旧 refresh_token 失效（jwt.pwv 校验）。
    must_change_password：seed 出的默认 admin / 管理员重置后强制下次登录改密。
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    # username / email 完整 unique；软删时改名 "__deleted_<id>_<original>" 释放
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active"
    )  # active / disabled
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="zh-CN")
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    roles: Mapped[list["Role"]] = relationship(
        secondary="user_roles", back_populates="users", lazy="selectin"
    )

    __table_args__ = (Index("ix_users_status", "status"),)


class Role(Base, TimestampMixin):
    """角色（admin / developer / viewer + 用户自建）"""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    users: Mapped[list["User"]] = relationship(
        secondary="user_roles", back_populates="roles", lazy="noload"
    )
    permissions: Mapped[list["Permission"]] = relationship(
        secondary="role_permissions", back_populates="roles", lazy="selectin"
    )


class Permission(Base):
    """权限点：<resource>:<action>，如 agents:write / models:read

    permission 表完全由 seed 写入，不允许 admin 在前端 CRUD。
    """

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    roles: Mapped[list["Role"]] = relationship(
        secondary="role_permissions", back_populates="permissions", lazy="noload"
    )

    __table_args__ = (Index("ix_permissions_resource", "resource"),)


class UserRole(Base):
    """user ↔ role 多对多连接表"""

    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    granted_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (PrimaryKeyConstraint("user_id", "role_id", name="pk_user_roles"),)


class RolePermission(Base):
    """role ↔ permission 多对多连接表"""

    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    permission_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (
        PrimaryKeyConstraint("role_id", "permission_id", name="pk_role_permissions"),
    )
