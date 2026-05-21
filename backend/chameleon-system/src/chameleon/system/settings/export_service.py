"""备份导出：DB → zip

zip 内容：
- model.json         providers + models（API key 仍然加密文，但与本机 master key 解耦）
- agents.yaml        external agents（source != 'local'）
- users.json         users + roles + user_roles + role_permissions（含 password_hash）
- apps.json          apps + api_keys（key_hash 不可还原 plaintext）
- embed_configs.json embed 配置
- README.md          说明导出文件意义 + 还原方法
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chameleon.core.models import (
    Agent,
    ApiKey,
    App,
    EmbedConfig,
    LLMModel,
    Provider,
    Role,
    RolePermission,
    User,
    UserRole,
)


# ── 各域 → dict ────────────────────────────────────────────


async def _export_model_json(session: AsyncSession) -> dict:
    providers = (
        (await session.execute(select(Provider).where(Provider.deleted_at.is_(None))))
        .scalars()
        .all()
    )
    models = (
        (await session.execute(select(LLMModel).where(LLMModel.deleted_at.is_(None))))
        .scalars()
        .all()
    )
    provider_code_by_id = {p.id: p.code for p in providers}

    return {
        "providers": {
            p.code: {
                "base_url": p.base_url or "",
                # 注意：导出加密文，不解密——目标机器要有相同 master key 才能解
                "api_key_encrypted": p.api_key_encrypted or "",
                "extra_config": p.extra_config or {},
                "enabled": p.enabled,
            }
            for p in providers
        },
        "models": {
            "llm": [
                _model_to_dict(m, provider_code_by_id)
                for m in models
                if m.kind == "chat"
            ],
            "embedding": [
                _model_to_dict(m, provider_code_by_id)
                for m in models
                if m.kind == "embedding"
            ],
        },
    }


def _model_to_dict(m: LLMModel, provider_code_by_id: dict[int, str]) -> dict:
    out: dict[str, Any] = {
        "name": m.code,
        "provider": provider_code_by_id.get(m.provider_id, ""),
    }
    if m.dim is not None:
        out["dim"] = m.dim
    if m.defaults:
        out.update(m.defaults)
    return out


async def _export_agents_yaml(session: AsyncSession) -> list[dict]:
    """仅导出外部 agents；本地 agent 由 namespace 扫描重建，不进 yaml"""
    rows = (
        (
            await session.execute(
                select(Agent).where(
                    Agent.deleted_at.is_(None), Agent.source != "local"
                )
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "key": a.agent_key,
            "provider": a.source,
            "name": a.name,
            "description": a.description,
            "tags": a.tags,
            "version": a.version,
            **(a.config or {}),
        }
        for a in rows
    ]


async def _export_users_json(session: AsyncSession) -> dict:
    users = (
        (
            await session.execute(
                select(User)
                .where(User.deleted_at.is_(None))
                .options(selectinload(User.roles))
            )
        )
        .scalars()
        .all()
    )
    roles = (await session.execute(select(Role))).scalars().all()
    role_permissions = (await session.execute(select(RolePermission))).all()

    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "password_hash": u.password_hash,
                "password_version": u.password_version,
                "must_change_password": u.must_change_password,
                "status": u.status,
                "locale": u.locale,
                "display_name": u.display_name,
                "role_codes": [r.code for r in u.roles],
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
        "roles": [
            {
                "code": r.code,
                "name": r.name,
                "description": r.description,
                "is_system": r.is_system,
            }
            for r in roles
        ],
        # 仅作参考（permission 由 seed 重建，role_permissions 由 role.code 重新链接）
        "role_permissions_summary": len(role_permissions),
    }


async def _export_apps_json(session: AsyncSession) -> dict:
    apps = (
        (await session.execute(select(App).where(App.deleted_at.is_(None))))
        .scalars()
        .all()
    )
    keys = (
        (await session.execute(select(ApiKey).where(ApiKey.revoked_at.is_(None))))
        .scalars()
        .all()
    )
    return {
        "apps": [
            {
                "id": a.id,
                "app_key": a.app_key,
                "name": a.name,
                "description": a.description,
                "status": a.status,
                "meta": a.meta,
                "qpm_limit": a.qpm_limit,
                "qpd_limit": a.qpd_limit,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in apps
        ],
        "api_keys": [
            {
                "id": k.id,
                "app_id": k.app_id,
                "name": k.name,
                "key_hash": k.key_hash,
                "key_prefix": k.key_prefix,
                "scopes": k.scopes,
                "description": k.description,
                "created_at": k.created_at.isoformat() if k.created_at else None,
            }
            for k in keys
        ],
    }


async def _export_embed_configs(session: AsyncSession) -> list[dict]:
    rows = (
        (
            await session.execute(
                select(EmbedConfig).where(EmbedConfig.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "embed_key": ec.embed_key,
            "name": ec.name,
            "description": ec.description,
            "agent_id": ec.agent_id,
            "app_id": ec.app_id,
            "allowed_origins": ec.allowed_origins,
            "ui_config": ec.ui_config,
            "behavior": ec.behavior,
            "enabled": ec.enabled,
        }
        for ec in rows
    ]


# ── 主入口 ────────────────────────────────────────────────


_README_MARKDOWN = """# Chameleon 配置导出

本 zip 由 `POST /v1/admin/settings/export-json` 导出。

## 文件清单

- `model.json`：providers + models 表（API key 仍为加密文）
- `agents.yaml`：外部 agent 注册（external，本地 agent 由 namespace 扫描重建）
- `users.json`：用户 + 角色（含密码 hash，**不要泄漏**）
- `apps.json`：业务应用 + API key（key_hash 不可还原明文）
- `embed_configs.json`：嵌入式 widget 配置

## 还原方法

1. 新机器部署 chameleon（同版本，迁移 head 一致）
2. 设置同样的 `CHAMELEON_CRYPTO_KEY`（providers.api_key 才能解密）
3. 调 `POST /v1/admin/settings/import-json` 上传本 zip + `confirm=true`

## 注意

- `users.json` 含密码 hash（argon2id 算法），属于敏感数据
- `apps.json` 的 key_hash 是 sha256 单向哈希，无法还原 plaintext；导入后业务方需要换发新 key
"""


async def build_export_zip(session: AsyncSession) -> tuple[bytes, str]:
    """构造完整导出 zip

    Returns:
        (zip_bytes, suggested_filename)
    """
    model = await _export_model_json(session)
    agents = await _export_agents_yaml(session)
    users = await _export_users_json(session)
    apps = await _export_apps_json(session)
    embeds = await _export_embed_configs(session)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("model.json", json.dumps(model, ensure_ascii=False, indent=2))
        zf.writestr(
            "agents.yaml", yaml.safe_dump(agents, allow_unicode=True, sort_keys=False)
        )
        zf.writestr("users.json", json.dumps(users, ensure_ascii=False, indent=2))
        zf.writestr("apps.json", json.dumps(apps, ensure_ascii=False, indent=2))
        zf.writestr(
            "embed_configs.json",
            json.dumps(embeds, ensure_ascii=False, indent=2),
        )
        zf.writestr("README.md", _README_MARKDOWN)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    return buf.getvalue(), f"chameleon-backup-{ts}.zip"
