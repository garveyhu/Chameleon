"""运行时 system_settings 读取 helper

为业务层一行调用读 settings 表（scope='global'）—— DB 没行时用 schema default。

例：
    days = await get_int(session, "call_log.retention_days")
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.config.system_settings_schema import schema_default
from chameleon.core.models import Setting


async def get_value(session: AsyncSession, key: str, default: Any = None) -> Any:
    """读 settings.value（JSON 列存 {"v": <值>}），无行则用 default 或 schema default"""
    row = (
        await session.execute(
            select(Setting).where(Setting.scope == "global", Setting.key == key)
        )
    ).scalar_one_or_none()
    if row is None:
        # 优先用调用方传的 default；否则取 schema 定义的 default
        return default if default is not None else schema_default(key)
    raw = row.value
    if isinstance(raw, dict) and set(raw.keys()) == {"v"}:
        return raw["v"]
    return raw


async def get_bool(session: AsyncSession, key: str, *, default: bool = False) -> bool:
    v = await get_value(session, key, default=default)
    return bool(v)


async def get_int(session: AsyncSession, key: str, *, default: int = 0) -> int:
    v = await get_value(session, key, default=default)
    try:
        return int(v)
    except (TypeError, ValueError):
        return default
