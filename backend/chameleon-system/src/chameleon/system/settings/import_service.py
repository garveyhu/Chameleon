"""备份导入：zip → DB

策略：UPSERT（按业务 key 找现有 row，存在则 update / 不存在则 insert）。
顺序：users → providers → models → external agents → embed_configs → api_keys。
注意：permissions / roles 不导入（由 seed.defaults 决定，避免新版本权限点跟旧 zip 不一致）。
apps「应用容器」已删，api_key 独立（app_id 仅为来源标签字符串）。
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import yaml
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.models import (
    Agent,
    ApiKey,
    EmbedConfig,
    LLMModel,
    Provider,
    Role,
    User,
    UserRole,
)


class ImportSummary:
    def __init__(self) -> None:
        self.users_upserted = 0
        self.providers_upserted = 0
        self.models_upserted = 0
        self.agents_upserted = 0
        self.embed_configs_upserted = 0
        self.api_keys_upserted = 0
        self.warnings: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "users_upserted": self.users_upserted,
            "providers_upserted": self.providers_upserted,
            "models_upserted": self.models_upserted,
            "agents_upserted": self.agents_upserted,
            "embed_configs_upserted": self.embed_configs_upserted,
            "api_keys_upserted": self.api_keys_upserted,
            "warnings": list(self.warnings),
        }


async def apply_import_zip(
    session: AsyncSession,
    zip_bytes: bytes,
) -> ImportSummary:
    summary = ImportSummary()

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = set(zf.namelist())
        files = {n: zf.read(n) for n in names}

    # 顺序很重要：依赖在前。apps「容器」已删，api_key 独立。
    if "users.json" in files:
        await _import_users(session, files["users.json"], summary)
    if "model.json" in files:
        await _import_providers_models(session, files["model.json"], summary)
    if "agents.yaml" in files:
        await _import_external_agents(session, files["agents.yaml"], summary)
    if "embed_configs.json" in files:
        await _import_embed_configs(session, files["embed_configs.json"], summary)
    # api_keys：新备份在 api_keys.json；老备份在 apps.json（含 api_keys 键）兜底
    api_keys_raw = files.get("api_keys.json") or files.get("apps.json")
    if api_keys_raw is not None:
        await _import_api_keys(session, api_keys_raw, summary)

    await session.flush()
    return summary


# ── 各域 import ────────────────────────────────────────────


async def _import_users(
    session: AsyncSession, raw: bytes, s: ImportSummary
) -> None:
    data = json.loads(raw)

    # 角色：仅追加缺失（permissions 由 seed 决定，不在这层）
    existing_role_codes = set(
        (await session.execute(select(Role.code))).scalars().all()
    )
    for r in data.get("roles", []):
        code = r["code"]
        if code in existing_role_codes:
            continue
        session.add(
            Role(
                code=code,
                name=r.get("name") or code,
                description=r.get("description"),
                is_system=bool(r.get("is_system")),
            )
        )
    await session.flush()

    role_id_by_code = dict(
        (await session.execute(select(Role.code, Role.id))).all()
    )

    # 用户：upsert + 同步角色关联
    for u in data.get("users", []):
        username = u["username"]
        existing = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if existing is None:
            user = User(
                username=username,
                email=u.get("email"),
                password_hash=u["password_hash"],
                password_version=u.get("password_version", 0),
                must_change_password=u.get("must_change_password", False),
                status=u.get("status") or "active",
                locale=u.get("locale") or "zh-CN",
                display_name=u.get("display_name"),
            )
            session.add(user)
            await session.flush()
        else:
            existing.email = u.get("email") or existing.email
            existing.password_hash = u["password_hash"]
            existing.password_version = u.get("password_version", existing.password_version)
            existing.status = u.get("status") or existing.status
            existing.locale = u.get("locale") or existing.locale
            existing.display_name = u.get("display_name") or existing.display_name
            user = existing

        # 同步角色（差量）
        await session.execute(
            UserRole.__table__.delete().where(UserRole.user_id == user.id)
        )
        for rc in u.get("role_codes", []):
            rid = role_id_by_code.get(rc)
            if rid is None:
                s.warnings.append(f"user {username} 引用未知 role {rc}，跳过")
                continue
            session.add(UserRole(user_id=user.id, role_id=rid))
        s.users_upserted += 1
    await session.flush()


async def _import_providers_models(
    session: AsyncSession, raw: bytes, s: ImportSummary
) -> None:
    data = json.loads(raw)
    code_to_id: dict[str, int] = {}

    for code, cfg in (data.get("providers") or {}).items():
        existing = (
            await session.execute(select(Provider).where(Provider.code == code))
        ).scalar_one_or_none()
        if existing is None:
            p = Provider(
                code=code,
                kind="llm",  # 默认；如有混合 kind 需要在 entry 显式指定
                name=code,
                base_url=cfg.get("base_url") or None,
                api_key_encrypted=cfg.get("api_key_encrypted") or None,
                extra_config=cfg.get("extra_config"),
                enabled=cfg.get("enabled", True),
            )
            session.add(p)
            await session.flush()
            code_to_id[code] = p.id
        else:
            existing.base_url = cfg.get("base_url") or existing.base_url
            existing.api_key_encrypted = (
                cfg.get("api_key_encrypted") or existing.api_key_encrypted
            )
            existing.extra_config = cfg.get("extra_config") or existing.extra_config
            existing.enabled = cfg.get("enabled", existing.enabled)
            code_to_id[code] = existing.id
        s.providers_upserted += 1
    await session.flush()

    models = data.get("models") or {}
    for kind_alias, items in models.items():
        kind_db = "chat" if kind_alias == "llm" else kind_alias  # llm → chat
        for item in items:
            code = item.get("name")
            provider_code = item.get("provider")
            if not code or provider_code not in code_to_id:
                s.warnings.append(f"model {code} 引用未知 provider {provider_code}")
                continue
            provider_id = code_to_id[provider_code]
            existing = (
                await session.execute(
                    select(LLMModel).where(
                        LLMModel.provider_id == provider_id,
                        LLMModel.code == code,
                    )
                )
            ).scalar_one_or_none()
            defaults = {
                k: v for k, v in item.items() if k not in {"name", "provider", "dim"}
            }
            if existing is None:
                session.add(
                    LLMModel(
                        provider_id=provider_id,
                        code=code,
                        kind=kind_db,
                        dim=item.get("dim"),
                        defaults=defaults or None,
                        enabled=True,
                    )
                )
            else:
                existing.dim = item.get("dim", existing.dim)
                existing.defaults = defaults or existing.defaults
            s.models_upserted += 1
    await session.flush()


async def _import_external_agents(
    session: AsyncSession, raw: bytes, s: ImportSummary
) -> None:
    items = yaml.safe_load(raw.decode("utf-8")) or []
    for entry in items:
        agent_key = entry.get("key")
        if not agent_key:
            continue
        existing = (
            await session.execute(
                select(Agent).where(Agent.agent_key == agent_key)
            )
        ).scalar_one_or_none()
        config = {
            k: v
            for k, v in entry.items()
            if k not in {"key", "provider", "name", "description", "tags", "version"}
        }
        if existing is None:
            session.add(
                Agent(
                    agent_key=agent_key,
                    name=entry.get("name") or agent_key,
                    description=entry.get("description"),
                    source=entry.get("provider"),
                    config=config or None,
                    tags=entry.get("tags"),
                    version=entry.get("version"),
                    enabled=True,
                )
            )
        else:
            existing.name = entry.get("name") or existing.name
            existing.description = entry.get("description") or existing.description
            existing.config = config or existing.config
            existing.tags = entry.get("tags") or existing.tags
        s.agents_upserted += 1
    await session.flush()


async def _import_embed_configs(
    session: AsyncSession, raw: bytes, s: ImportSummary
) -> None:
    items = json.loads(raw)
    for entry in items:
        embed_key = entry.get("embed_key")
        if not embed_key:
            continue
        existing = (
            await session.execute(
                select(EmbedConfig).where(EmbedConfig.embed_key == embed_key)
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                EmbedConfig(
                    embed_key=embed_key,
                    name=entry.get("name") or embed_key,
                    description=entry.get("description"),
                    agent_id=entry["agent_id"],
                    allowed_origins=entry.get("allowed_origins"),
                    ui_config=entry.get("ui_config"),
                    behavior=entry.get("behavior"),
                    enabled=entry.get("enabled", True),
                )
            )
        else:
            existing.name = entry.get("name") or existing.name
            existing.description = entry.get("description") or existing.description
            existing.allowed_origins = (
                entry.get("allowed_origins") or existing.allowed_origins
            )
            existing.ui_config = entry.get("ui_config") or existing.ui_config
            existing.behavior = entry.get("behavior") or existing.behavior
            existing.enabled = entry.get("enabled", existing.enabled)
        s.embed_configs_upserted += 1
    await session.flush()


async def _import_api_keys(
    session: AsyncSession, raw: bytes, s: ImportSummary
) -> None:
    """import api_keys（独立资源，app_id 仅为来源标签字符串，无 FK）"""
    data = json.loads(raw)
    existing_hashes = set(
        (await session.execute(select(ApiKey.key_hash))).scalars().all()
    )
    for k in data.get("api_keys", []):
        if k["key_hash"] in existing_hashes:
            continue
        session.add(
            ApiKey(
                app_id=k.get("app_id") or "imported",
                name=k.get("name") or "imported",
                key_hash=k["key_hash"],
                key_prefix=k.get("key_prefix") or "chm_imported",
                scopes=k.get("scopes") or [],
                scope_type=k.get("scope_type") or "global",
                scope_ref=k.get("scope_ref"),
                qpm_limit=k.get("qpm_limit"),
                qpd_limit=k.get("qpd_limit"),
                description=k.get("description"),
            )
        )
        s.api_keys_upserted += 1
    await session.flush()
    if s.api_keys_upserted:
        logger.warning(
            "imported {} api_keys (key_hash only) — 业务方需要管理员重新签发明文 key",
            s.api_keys_upserted,
        )
