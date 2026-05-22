"""system settings seed —— 读 chameleon.json，扁平 key 落 settings 表 (scope='global')

flatten 规则：
  { "session": { "history_limit": 20 } } → key="session.history_limit", value=20

仅首次启动跑（Phase B）；schema 不认识的 key 警告跳过。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.config.constants import CONFIG_PATH
from chameleon.core.config.system_settings_schema import schema_dict, schema_group
from chameleon.core.models import Setting


def _flatten(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """嵌套 dict → 点号 key 平铺，叶子是非 dict 值。"""
    out: dict[str, Any] = {}
    for k, v in d.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, full))
        else:
            out[full] = v
    return out


def _load_chameleon_json(config_dir: Path | None) -> dict | None:
    path = (config_dir or CONFIG_PATH) / "chameleon.json"
    if not path.exists():
        logger.warning("seed: {} 不存在，跳过 system_settings", path)
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def seed_system_settings(
    session: AsyncSession,
    *,
    config_dir: Path | None = None,
) -> None:
    """读 chameleon.json → 落 settings 表 (scope='global')

    schema 不认识的 key 跳过 + 警告。
    """
    raw = _load_chameleon_json(config_dir)
    if raw is None:
        return

    flat = _flatten(raw)
    known = schema_dict()

    existing_keys = set(
        (
            await session.execute(
                select(Setting.key).where(Setting.scope == "global")
            )
        )
        .scalars()
        .all()
    )

    inserted = 0
    for key, value in flat.items():
        if key in existing_keys:
            continue
        if key not in known:
            logger.warning("seed: unknown setting key in chameleon.json: {}", key)
            continue
        # value_type 根据 schema 推断；这里全部 JSON 序列化存
        group = schema_group(key) or "general"
        description = known[key].description_zh
        session.add(
            Setting(
                scope="global",
                key=key,
                value={"v": value},  # 包一层 dict（JSON 列）
                value_type=known[key].value_type,
                description=f"[{group}] {description}",
            )
        )
        inserted += 1

    if inserted:
        await session.flush()
        logger.info("seed: system_settings ({})", inserted)
