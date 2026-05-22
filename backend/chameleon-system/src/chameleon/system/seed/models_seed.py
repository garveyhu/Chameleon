"""providers + models seed

读 config/model.json 的 providers / models 段，落 DB providers + models 表。
providers.api_key 用 AES-256-GCM 加密存到 providers.api_key_encrypted。
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.config.constants import CONFIG_PATH
from chameleon.core.models import LLMModel, ModelDefault, Provider
from chameleon.core.utils.crypto import encrypt


def _load_model_json(config_dir: Path | None) -> dict | None:
    path = (config_dir or CONFIG_PATH) / "model.json"
    if not path.exists():
        logger.warning("seed: {} 不存在，跳过 providers/models", path)
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def seed_providers_and_models(
    session: AsyncSession,
    *,
    config_dir: Path | None = None,
) -> None:
    raw = _load_model_json(config_dir)
    if raw is None:
        return

    provider_id_by_code = await _seed_providers(session, raw.get("providers") or {})
    await _seed_models(session, raw.get("models") or {}, provider_id_by_code)
    await _seed_model_defaults(session, raw.get("cases") or {})


async def _seed_providers(
    session: AsyncSession,
    providers: dict[str, dict],
) -> dict[str, int]:
    """每个 providers.<code> 入 providers 表（kind='llm' 默认；embedding 也在同一 provider）

    Returns:
        {provider_code: provider_id} 映射给 models seed 用
    """
    existing = dict(
        (await session.execute(select(Provider.code, Provider.id))).all()
    )
    result: dict[str, int] = dict(existing)

    for code, cfg in providers.items():
        if code in existing:
            continue
        base_url = cfg.get("base_url") or None
        api_key_plain = cfg.get("api_key") or None
        api_key_encrypted = encrypt(api_key_plain) if api_key_plain else None
        provider = Provider(
            code=code,
            kind="llm",  # model.json 里的 provider 都是 LLM provider
            name=code,
            base_url=base_url,
            api_key_encrypted=api_key_encrypted,
            enabled=True,
        )
        session.add(provider)
        await session.flush()
        result[code] = provider.id
        logger.info(
            "seed: provider {} (api_key={})", code, "encrypted" if api_key_plain else "blank"
        )
    return result


async def _seed_model_defaults(
    session: AsyncSession,
    cases: dict[str, str | None],
) -> None:
    """从 model.json.cases 写入 model_defaults 表（首次启动）"""
    existing = set(
        (await session.execute(select(ModelDefault.case_name))).scalars().all()
    )
    inserted = 0
    for case_name, model_name in cases.items():
        if case_name in existing:
            continue
        if not model_name:
            session.add(ModelDefault(case_name=case_name, model_id=None))
            inserted += 1
            continue
        model_row = (
            await session.execute(
                select(LLMModel).where(
                    LLMModel.code == model_name, LLMModel.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        if model_row is None:
            logger.warning(
                "seed: cases.{} = '{}' 找不到对应 model，留 NULL", case_name, model_name
            )
            session.add(ModelDefault(case_name=case_name, model_id=None))
        else:
            session.add(
                ModelDefault(case_name=case_name, model_id=model_row.id)
            )
        inserted += 1
    if inserted:
        await session.flush()
        logger.info("seed: model_defaults ({})", inserted)


async def _seed_models(
    session: AsyncSession,
    models: dict[str, list[dict]],
    provider_id_by_code: dict[str, int],
) -> None:
    """models.llm[] + models.embedding[] 都入 models 表，kind 区分"""
    existing_pairs = set(
        (await session.execute(select(LLMModel.provider_id, LLMModel.code))).all()
    )
    inserted = 0

    for kind, items in models.items():
        if kind not in ("llm", "embedding"):
            logger.warning("seed: 未知 model kind '{}' 跳过", kind)
            continue
        normalized_kind = "chat" if kind == "llm" else "embedding"

        for item in items:
            code = item.get("name")
            provider_code = item.get("provider")
            if not code or not provider_code:
                logger.warning("seed: model 缺 name 或 provider {} 跳过", item)
                continue
            provider_id = provider_id_by_code.get(provider_code)
            if provider_id is None:
                logger.warning(
                    "seed: model {} 引用未知 provider {} 跳过", code, provider_code
                )
                continue
            if (provider_id, code) in existing_pairs:
                continue

            defaults = {
                k: v
                for k, v in item.items()
                if k not in {"name", "provider", "dim"}
            }
            session.add(
                LLMModel(
                    provider_id=provider_id,
                    code=code,
                    kind=normalized_kind,
                    dim=item.get("dim"),
                    defaults=defaults or None,
                    enabled=True,
                )
            )
            inserted += 1
    await session.flush()
    logger.info("seed: models ({})", inserted)
