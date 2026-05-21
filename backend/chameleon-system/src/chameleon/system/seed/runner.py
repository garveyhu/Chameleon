"""seed 主流程

启动期调用 run_seed_if_empty()，按依赖顺序执行：
  1. permissions（来自 defaults.py 静态清单）
  2. roles + role_permissions
  3. 默认 admin 用户（强随机密码 + must_change_password=True）
  4. providers / models（来自 config/model.json，api_key 加密）
  5. agents（本地 namespace 扫描 + config/agents.yaml 外部条目）

幂等：每步先查现有数据，已存在则跳过。
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


async def run_seed_if_empty(
    *,
    config_dir: Path | None = None,
) -> AdminCredentials | None:
    """启动期入口

    Returns:
        新 seed 出的 admin 凭据（首次启动）；None 表示 DB 已有数据跳过 seed
    """
    async with AsyncSessionLocal() as session:
        users_count = (
            await session.execute(select(User.id).limit(1))
        ).scalar_one_or_none()
        if users_count is not None:
            logger.debug("seed skipped (users table not empty)")
            return None

        logger.info("DB empty → running first-time seed ...")
        await _seed_permissions(session)
        await _seed_roles(session)
        admin_creds = await _seed_default_admin(session)
        await seed_providers_and_models(session, config_dir=config_dir)
        await seed_agents(session, config_dir=config_dir)
        await session.commit()

    # 写凭据文件（在 commit 后，确保 DB 真的落盘成功才提示用户）
    write_credentials_file(admin_creds)
    logger.warning(
        "★ 首次启动，默认 admin 已创建：username={} → 详见 logs/initial-admin-credentials.txt",
        admin_creds.username,
    )
    return admin_creds


# ── 各 seed 步骤 ───────────────────────────────────────────


async def _seed_permissions(session: AsyncSession) -> None:
    """插全部 permission 点"""
    existing_codes = set(
        (await session.execute(select(Permission.code))).scalars().all()
    )
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
    await session.flush()
    logger.info("seed: permissions ({})", len(all_permissions()))


async def _seed_roles(session: AsyncSession) -> None:
    """建 admin / developer / viewer 角色 + 关联 permissions"""
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
                # 通配权限：admin 用，绑全部具体 permission
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
    logger.info("seed: roles + role_permissions")


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
