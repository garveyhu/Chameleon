"""seed 主流程

启动期调用 run_seed_if_empty()，分两阶段：

  阶段 A —— **每次启动都跑（幂等增量）**：
    1. permissions：补 defaults.py 新增的权限点
    2. admin 角色：按 *:* 通配重新绑定到 DB 全部 permissions
       （这样 defaults.py 加新权限点后，admin 自动获得，无需手动同步）

  阶段 B —— **仅首次启动 DB 空时跑**：
    3. 除 admin 外的其他内置角色 (developer / viewer)
    4. 默认 admin 用户（强随机密码 + must_change_password=True）
    5. providers / models（来自 config/model.json，api_key 加密）
    6. agents（本地 namespace 扫描 + config/agents.yaml 外部条目）

幂等：A 阶段已存在跳过，B 阶段全 DB 不空就跳过。
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from chameleon.system.seed.admin_init import (
    AdminCredentials,
    create_default_admin,
    write_credentials_file,
)
from chameleon.system.seed.agents_seed import seed_agents
from chameleon.system.seed.defaults import (
    DEFAULT_ADMIN_USERNAME,
    all_permissions,
    default_roles,
)
from chameleon.system.seed.models_seed import seed_providers_and_models
from chameleon.system.seed.settings_seed import seed_system_settings


async def run_seed_if_empty(
    *,
    config_dir: Path | None = None,
) -> AdminCredentials | None:
    """启动期入口。

    Returns:
        新 seed 出的 admin 凭据（首次启动）；None 表示 DB 已存在用户跳过 B 阶段
    """
    async with AsyncSessionLocal() as session:
        # ── 阶段 A：每次启动都跑 ────────────────────────────
        await _sync_permissions(session)
        await _sync_admin_wildcard(session)

        users_count = (
            await session.execute(select(User.id).limit(1))
        ).scalar_one_or_none()

        if users_count is not None:
            # 已有用户 → B 阶段跳过，但 A 已经把新加的权限补齐
            await session.commit()
            logger.debug("seed: incremental sync done (users table not empty)")
            return None

        # ── 阶段 B：首次启动 ────────────────────────────────
        logger.info("DB empty → running first-time seed ...")
        await _seed_other_roles(session)
        admin_creds = await _seed_default_admin(session)
        await seed_system_settings(session, config_dir=config_dir)
        await seed_providers_and_models(session, config_dir=config_dir)
        await seed_agents(session, config_dir=config_dir)
        await session.commit()

    write_credentials_file(admin_creds)
    logger.warning(
        "★ 首次启动，默认 admin 已创建：username={} → 详见 logs/initial-admin-credentials.txt",
        admin_creds.username,
    )
    return admin_creds


# ── 阶段 A：幂等同步 ───────────────────────────────────────


async def _sync_permissions(session: AsyncSession) -> int:
    """upsert defaults.py 的权限点到 DB。

    Returns: 新增的权限数量
    """
    existing_codes = set(
        (await session.execute(select(Permission.code))).scalars().all()
    )
    added = 0
    for code, resource, action, description in all_permissions():
        if code in existing_codes:
            continue
        session.add(
            Permission(
                code=code,
                resource=resource,
                action=action,
                description=description,
            )
        )
        added += 1
    if added:
        await session.flush()
        logger.info("seed: permissions +{}（新增）", added)
    return added


async def _sync_admin_wildcard(session: AsyncSession) -> None:
    """让 admin 角色始终包含 DB 全部 permissions。

    defaults.py 里 admin 写的是 ['*:*'] → 当 DB 新增权限点时，
    admin 应自动获得；本函数做这个同步。
    若 admin 角色还不存在（首次启动），跳过 —— B 阶段会建。
    """
    admin_role = (
        await session.execute(select(Role).where(Role.code == "admin"))
    ).scalar_one_or_none()
    if admin_role is None:
        return

    all_perm_ids = set(
        (await session.execute(select(Permission.id))).scalars().all()
    )
    bound_ids = set(
        (
            await session.execute(
                select(RolePermission.permission_id).where(
                    RolePermission.role_id == admin_role.id
                )
            )
        )
        .scalars()
        .all()
    )
    missing = all_perm_ids - bound_ids
    for perm_id in missing:
        session.add(
            RolePermission(role_id=admin_role.id, permission_id=perm_id)
        )
    if missing:
        await session.flush()
        logger.info("seed: admin 角色新增 {} 个权限绑定", len(missing))


# ── 阶段 B：首次 seed ─────────────────────────────────────


async def _seed_other_roles(session: AsyncSession) -> None:
    """建 developer / viewer 角色（admin 由阶段 A 兜底）"""
    existing_role_codes = set(
        (await session.execute(select(Role.code))).scalars().all()
    )
    perm_id_by_code = dict(
        (await session.execute(select(Permission.code, Permission.id))).all()
    )

    for code, name, description, perm_codes in default_roles():
        if code in existing_role_codes:
            continue
        role = Role(code=code, name=name, description=description, is_system=True)
        session.add(role)
        await session.flush()
        for pc in perm_codes:
            if pc == "*:*":
                for perm_id in perm_id_by_code.values():
                    session.add(
                        RolePermission(role_id=role.id, permission_id=perm_id)
                    )
            elif pc in perm_id_by_code:
                session.add(
                    RolePermission(
                        role_id=role.id, permission_id=perm_id_by_code[pc]
                    )
                )
    await session.flush()
    logger.info("seed: 内置角色已建")


async def _seed_default_admin(session: AsyncSession) -> AdminCredentials:
    """建默认 admin 用户，分配 admin 角色，返凭据（含明文密码，仅一次回显）"""
    user, credentials = create_default_admin()
    session.add(user)
    await session.flush()

    admin_role_id = (
        await session.execute(select(Role.id).where(Role.code == "admin"))
    ).scalar_one()
    session.add(UserRole(user_id=user.id, role_id=admin_role_id))
    await session.flush()
    return credentials


# 兼容旧 import（无外部调用，留作 grep 友好）
__all__ = [
    "run_seed_if_empty",
    "DEFAULT_ADMIN_USERNAME",
]
