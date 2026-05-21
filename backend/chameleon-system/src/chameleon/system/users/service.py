"""users 业务编排"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.core.api.response import PageParams, PageResult
from chameleon.core.models import Role, User, UserRole
from chameleon.core.utils.passwords import hash_password
from chameleon.system.users.schemas import (
    CreateUserRequest,
    ResetPasswordRequest,
    UpdateUserRequest,
    UserItem,
)


def _user_to_item(user: User) -> UserItem:
    return UserItem(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        locale=user.locale,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        role_codes=[r.code for r in (user.roles or [])],
    )


async def list_users(
    session: AsyncSession, page: PageParams
) -> PageResult[UserItem]:
    base = select(User).where(User.deleted_at.is_(None))
    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                base.options(selectinload(User.roles))
                .order_by(User.created_at.desc())
                .offset(page.offset)
                .limit(page.limit)
            )
        )
        .scalars()
        .all()
    )
    return PageResult(
        items=[_user_to_item(u) for u in rows],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


async def get_user(session: AsyncSession, user_id: int) -> UserItem:
    user = (
        await session.execute(
            select(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
            .options(selectinload(User.roles))
        )
    ).scalar_one_or_none()
    if user is None:
        raise BusinessError(ResultCode.AgentNotFound, message=f"用户不存在: {user_id}")
    return _user_to_item(user)


async def create_user(
    session: AsyncSession, req: CreateUserRequest
) -> UserItem:
    # 校验 username 唯一
    exists = (
        await session.execute(select(User.id).where(User.username == req.username))
    ).scalar_one_or_none()
    if exists is not None:
        raise ValidationError(message=f"username 已存在: {req.username}")

    user = User(
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
        display_name=req.display_name,
        locale=req.locale,
        must_change_password=req.must_change_password,
        status="active",
    )
    session.add(user)
    await session.flush()

    # 关联角色
    if req.role_codes:
        await _assign_roles(session, user.id, req.role_codes)

    # 重新加载含 roles
    user = (
        await session.execute(
            select(User)
            .where(User.id == user.id)
            .options(selectinload(User.roles))
        )
    ).scalar_one()
    logger.info("user created | id={} | username={}", user.id, user.username)
    return _user_to_item(user)


async def update_user(
    session: AsyncSession, user_id: int, req: UpdateUserRequest
) -> UserItem:
    user = (
        await session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if user is None:
        raise BusinessError(ResultCode.AgentNotFound, message=f"用户不存在: {user_id}")

    if req.email is not None:
        user.email = req.email
    if req.display_name is not None:
        user.display_name = req.display_name
    if req.locale is not None:
        user.locale = req.locale
    if req.status is not None:
        user.status = req.status

    await session.flush()
    return await get_user(session, user_id)


async def delete_user(session: AsyncSession, user_id: int) -> None:
    user = (
        await session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if user is None:
        raise BusinessError(ResultCode.AgentNotFound, message=f"用户不存在: {user_id}")
    if user.username == "admin":
        raise ValidationError(message="默认 admin 用户不可删除")
    user.deleted_at = datetime.now(timezone.utc)
    user.username = f"__deleted_{user.id}_{user.username}"  # 释放原 username
    await session.flush()
    logger.info("user soft-deleted | id={}", user_id)


async def reset_password(
    session: AsyncSession, user_id: int, req: ResetPasswordRequest
) -> None:
    """admin 重置任意用户密码（bump password_version 让旧 refresh 失效）"""
    user = (
        await session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if user is None:
        raise BusinessError(ResultCode.AgentNotFound, message=f"用户不存在: {user_id}")
    user.password_hash = hash_password(req.new_password)
    user.password_version = user.password_version + 1
    user.must_change_password = req.must_change_password
    await session.flush()
    logger.info("user password reset | id={}", user_id)


async def grant_role(
    session: AsyncSession, user_id: int, role_code: str
) -> UserItem:
    role = (
        await session.execute(select(Role).where(Role.code == role_code))
    ).scalar_one_or_none()
    if role is None:
        raise ValidationError(message=f"role 不存在: {role_code}")

    # 幂等：已有的不再插
    existing = (
        await session.execute(
            select(UserRole).where(
                UserRole.user_id == user_id, UserRole.role_id == role.id
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(UserRole(user_id=user_id, role_id=role.id))
        await session.flush()
    return await get_user(session, user_id)


async def revoke_role(
    session: AsyncSession, user_id: int, role_code: str
) -> UserItem:
    role = (
        await session.execute(select(Role).where(Role.code == role_code))
    ).scalar_one_or_none()
    if role is None:
        raise ValidationError(message=f"role 不存在: {role_code}")
    await session.execute(
        UserRole.__table__.delete().where(
            UserRole.user_id == user_id, UserRole.role_id == role.id
        )
    )
    await session.flush()
    return await get_user(session, user_id)


async def _assign_roles(
    session: AsyncSession, user_id: int, role_codes: list[str]
) -> None:
    if not role_codes:
        return
    role_id_by_code = dict(
        (
            await session.execute(
                select(Role.code, Role.id).where(Role.code.in_(role_codes))
            )
        ).all()
    )
    for rc in role_codes:
        rid = role_id_by_code.get(rc)
        if rid is None:
            raise ValidationError(message=f"role 不存在: {rc}")
        session.add(UserRole(user_id=user_id, role_id=rid))
    await session.flush()
