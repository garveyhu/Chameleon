"""默认 admin 用户生成 + 凭据写文件"""

from __future__ import annotations

import os
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger

from chameleon.core.config.constants import LOG_DIR
from chameleon.data.models import User
from chameleon.data.utils.passwords import hash_password
from chameleon.system.seed.defaults import (
    DEFAULT_ADMIN_DISPLAY_NAME,
    DEFAULT_ADMIN_LOCALE,
    DEFAULT_ADMIN_USERNAME,
)

# 密码字符集：大小写 + 数字 + 部分安全特殊字符（避免引号 / 反斜杠）
_PWD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
_PWD_LEN = 20

_CREDENTIALS_FILE = "initial-admin-credentials.txt"


@dataclass(frozen=True)
class AdminCredentials:
    username: str
    plaintext_password: str  # 仅一次！seed 完即应清掉变量
    created_at: datetime


def _gen_strong_password(length: int = _PWD_LEN) -> str:
    """generate 20 字符强密码（≈ 124 bit entropy）"""
    return "".join(secrets.choice(_PWD_ALPHABET) for _ in range(length))


def create_default_admin() -> tuple[User, AdminCredentials]:
    """构造默认 admin User ORM 对象 + 凭据（不 add session，调用方 add）"""
    plaintext = _gen_strong_password()
    user = User(
        username=DEFAULT_ADMIN_USERNAME,
        password_hash=hash_password(plaintext),
        password_version=0,
        must_change_password=True,
        status="active",
        locale=DEFAULT_ADMIN_LOCALE,
        display_name=DEFAULT_ADMIN_DISPLAY_NAME,
    )
    credentials = AdminCredentials(
        username=DEFAULT_ADMIN_USERNAME,
        plaintext_password=plaintext,
        created_at=datetime.now(timezone.utc),
    )
    return user, credentials


def write_credentials_file(creds: AdminCredentials) -> None:
    """凭据写到 backend/logs/initial-admin-credentials.txt（chmod 600）"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    target = LOG_DIR / _CREDENTIALS_FILE
    content = (
        "# Chameleon 默认管理员凭据（首次启动生成）\n"
        "# ⚠️  这是唯一一次显示密码的机会；首次登录后请立即改密。\n"
        "# 文件权限已设为 600，确保只有当前用户能读。\n"
        f"# 生成时间（UTC）：{creds.created_at.isoformat()}\n"
        "\n"
        f"username = {creds.username}\n"
        f"password = {creds.plaintext_password}\n"
    )
    target.write_text(content, encoding="utf-8")
    try:
        os.chmod(target, 0o600)
    except OSError as e:
        logger.warning("chmod 600 failed for {}: {}", target, e)
    logger.info("admin credentials written to {}", target)
