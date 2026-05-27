"""备份导出：DB → zip

zip 内容：
- model.json         providers + models（API key 仍然加密文，但与本机 master key 解耦）
- agents.yaml        external agents（source != 'local'）
- users.json         users + roles + user_roles + role_permissions（含 password_hash）
- api_keys.json      api_keys（key_hash 不可还原 plaintext；app_id 为来源标签）
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

from chameleon.core.config.system_settings_schema import schema_dict
from chameleon.core.models import (
    Agent,
    ApiKey,
    EmbedConfig,
    LLMModel,
    ModelDefault,
    Provider,
    Role,
    RolePermission,
    Setting,
    User,
)
from chameleon.core.utils.crypto import get_or_decrypt

# ── 各域 → dict ────────────────────────────────────────────


async def _export_model_json(session: AsyncSession) -> dict:
    """导出 providers + models + cases；api_key 解密为明文（按 P16-A 决策）"""
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
    defaults = (await session.execute(select(ModelDefault))).scalars().all()
    provider_code_by_id = {p.id: p.code for p in providers}
    model_code_by_id = {m.id: m.code for m in models}

    cases = {d.case_name: (model_code_by_id.get(d.model_id) if d.model_id else None) for d in defaults}

    return {
        "cases": cases,
        "providers": {
            p.code: {
                "base_url": p.base_url or "",
                "api_key": get_or_decrypt(p.api_key_encrypted) or "",
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


async def _export_chameleon_json(session: AsyncSession) -> dict:
    """settings 表 (scope='global') → 嵌套 chameleon.json 结构"""
    rows = (
        (await session.execute(select(Setting).where(Setting.scope == "global")))
        .scalars()
        .all()
    )
    known = schema_dict()
    flat: dict[str, Any] = {}
    # 先以 DB 值覆盖
    for r in rows:
        if r.key not in known:
            continue
        raw = r.value
        flat[r.key] = raw.get("v") if isinstance(raw, dict) and "v" in raw else raw
    # schema 里 DB 缺失的 key 用 default 填回（导出意图：完整快照）
    for k, s in known.items():
        flat.setdefault(k, s.default)

    # 点号 key 还原成嵌套
    nested: dict[str, Any] = {}
    for key, value in flat.items():
        parts = key.split(".")
        cursor = nested
        for p in parts[:-1]:
            cursor = cursor.setdefault(p, {})
        cursor[parts[-1]] = value
    return nested


async def _export_baseurl_json(session: AsyncSession) -> dict:
    """providers.base_url 去重抽出，作为参考字典（导入时无强引用）"""
    providers = (
        (await session.execute(select(Provider).where(Provider.deleted_at.is_(None))))
        .scalars()
        .all()
    )
    return {p.code: p.base_url for p in providers if p.base_url}


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


async def _export_api_keys_json(session: AsyncSession) -> dict:
    """导出未吊销的 api_keys（app_id 当普通来源标签；apps 容器已删）。"""
    keys = (
        (await session.execute(select(ApiKey).where(ApiKey.revoked_at.is_(None))))
        .scalars()
        .all()
    )
    return {
        "api_keys": [
            {
                "id": k.id,
                "app_id": k.app_id,
                "name": k.name,
                "key_hash": k.key_hash,
                "key_prefix": k.key_prefix,
                "scopes": k.scopes,
                "scope_type": k.scope_type,
                "scope_ref": k.scope_ref,
                "qpm_limit": k.qpm_limit,
                "qpd_limit": k.qpd_limit,
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

## ⚠️ 重要安全提示

**本 zip 内含明文 API Key（providers.api_key）与密码哈希（users.password_hash）。
请勿上传到 git / IM / 公网云盘。**

## 文件清单

- `chameleon.json`：系统运行时配置（log_level / session / knowledge / stream / timeout / call_log）
- `model.json`：providers + models + cases（API key **明文**）
- `baseurl.json`：providers 的 base_url 去重抽出（参考用，导入时不强引用）
- `agents.yaml`：外部 agent 注册（external，本地 agent 由 namespace 扫描重建）
- `users.json`：用户 + 角色（含密码 hash，**不要泄漏**）
- `api_keys.json`：API key（key_hash 不可还原明文；app_id 为来源标签）
- `embed_configs.json`：嵌入式 widget 配置

## 还原方法（导入二期；本期暂时手工）

A. 把 4 个 json/yaml 放回新部署机的 `backend/config/` 目录
B. 清空目标库（确保 DB 完全空）
C. 启动 chameleon —— seed runner 会读 config/*.{json,yaml} 重建

或：调 `POST /v1/admin/settings/import-json` 上传本 zip + `confirm=true`（二期 v0.3）

## 注意

- `users.json` 含密码 hash（argon2id 算法），属于敏感数据
- `api_keys.json` 的 key_hash 是 sha256 单向哈希，无法还原 plaintext；导入后业务方需要换发新 key
- `cases.llm / embedding / vision` 字段表示"默认使用哪个 model"
"""


async def build_export_zip(session: AsyncSession) -> tuple[bytes, str]:
    """构造完整导出 zip

    Returns:
        (zip_bytes, suggested_filename)
    """
    chameleon_cfg = await _export_chameleon_json(session)
    model = await _export_model_json(session)
    baseurl = await _export_baseurl_json(session)
    agents = await _export_agents_yaml(session)
    users = await _export_users_json(session)
    api_keys = await _export_api_keys_json(session)
    embeds = await _export_embed_configs(session)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "chameleon.json", json.dumps(chameleon_cfg, ensure_ascii=False, indent=2)
        )
        zf.writestr("model.json", json.dumps(model, ensure_ascii=False, indent=2))
        zf.writestr("baseurl.json", json.dumps(baseurl, ensure_ascii=False, indent=2))
        zf.writestr(
            "agents.yaml", yaml.safe_dump(agents, allow_unicode=True, sort_keys=False)
        )
        zf.writestr("users.json", json.dumps(users, ensure_ascii=False, indent=2))
        zf.writestr(
            "api_keys.json", json.dumps(api_keys, ensure_ascii=False, indent=2)
        )
        zf.writestr(
            "embed_configs.json",
            json.dumps(embeds, ensure_ascii=False, indent=2),
        )
        zf.writestr("README.md", _README_MARKDOWN)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    return buf.getvalue(), f"chameleon-backup-{ts}.zip"
