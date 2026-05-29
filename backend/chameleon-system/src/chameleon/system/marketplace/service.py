"""marketplace service —— 注册 / 同步 / 搜索 / 安装

设计：
- sync_registry：拉远端 index → 缓存 entries + pinning 到 DB
- search：扫所有 enabled registry 的 cached_entries，按关键词 / tag 过滤
- install_from_remote：取缓存 entry → 拉 manifest + 验签 → 复用 PluginRegistry.install

红线（plan §2 P20）：
- 远端 manifest 必须经 publisher pubkey 签名验证
- 不允许 inline manifest 绕过验签
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.plugins import PluginManifest
from chameleon.data.models import PluginInstance, PluginRegistryEntry
from chameleon.integrations.plugins import plugin_registry
from chameleon.integrations.plugins.registry_client import (
    RegistryClientError,
    RemotePluginEntry,
    fetch_and_verify_manifest,
    fetch_index,
)
from chameleon.system.marketplace.schemas import (
    AddRegistryRequest,
    InstallFromRemoteRequest,
    MarketplaceEntry,
    RegistryItem,
    SyncResult,
    UpdateRegistryRequest,
)

# ── registry CRUD ──────────────────────────────────────


async def list_registries(session: AsyncSession) -> list[RegistryItem]:
    rows = (
        (
            await session.execute(
                select(PluginRegistryEntry).order_by(
                    PluginRegistryEntry.created_at.asc()
                )
            )
        )
        .scalars()
        .all()
    )
    return [RegistryItem.model_validate(r) for r in rows]


async def add_registry(
    session: AsyncSession, req: AddRegistryRequest
) -> RegistryItem:
    exists = (
        await session.execute(
            select(PluginRegistryEntry).where(
                PluginRegistryEntry.registry_url == req.registry_url
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise BusinessError(
            ResultCode.Fail,
            message=f"registry 已存在: {req.registry_url}",
        )
    row = PluginRegistryEntry(
        registry_url=req.registry_url,
        name=req.name,
        enabled=True,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    item = RegistryItem.model_validate(row)
    await session.commit()
    logger.info("registry added | id={} | url={}", row.id, row.registry_url)
    return item


async def update_registry(
    session: AsyncSession, registry_id: int, req: UpdateRegistryRequest
) -> RegistryItem:
    row = await _load_registry(session, registry_id)
    if req.name is not None:
        row.name = req.name
    if req.enabled is not None:
        row.enabled = req.enabled
    await session.flush()
    await session.refresh(row)
    item = RegistryItem.model_validate(row)
    await session.commit()
    return item


async def delete_registry(session: AsyncSession, registry_id: int) -> None:
    await _load_registry(session, registry_id)
    await session.execute(
        delete(PluginRegistryEntry).where(
            PluginRegistryEntry.id == registry_id
        )
    )
    await session.commit()


# ── sync ───────────────────────────────────────────────


async def sync_registry(
    session: AsyncSession, registry_id: int
) -> SyncResult:
    row = await _load_registry(session, registry_id)
    if not row.enabled:
        raise BusinessError(
            ResultCode.Fail,
            message=f"registry 已 disabled: {row.registry_url}",
        )
    try:
        publishers, entries = await fetch_index(row.registry_url)
    except RegistryClientError as e:
        raise BusinessError(
            ResultCode.Fail, message=f"sync 失败: {e}"
        ) from e

    now = datetime.now(timezone.utc)
    # entries 序列化成 list[dict] 入库 cached_entries
    cached = [
        {
            "name": e.name,
            "latest": e.latest,
            "type": e.type,
            "description": e.description,
            "manifest_url": e.manifest_url,
            "signature_url": e.signature_url,
            "publisher": e.publisher,
            "tags": e.tags,
            "downloads": e.downloads,
            "updated_at": e.updated_at,
            "publisher_pubkey": e.publisher_pubkey,
        }
        for e in entries
    ]
    await session.execute(
        update(PluginRegistryEntry)
        .where(PluginRegistryEntry.id == registry_id)
        .values(
            pubkey_pinning=publishers,
            cached_entries=cached,
            last_synced_at=now,
        )
    )
    await session.commit()
    return SyncResult(
        registry_id=registry_id,
        entries=len(entries),
        publishers=len(publishers),
        last_synced_at=now,
    )


# ── search ────────────────────────────────────────────


async def search(
    session: AsyncSession, *, query: str = "", tag: str | None = None
) -> list[MarketplaceEntry]:
    """跨所有 enabled registry 的缓存搜索 —— 不去远端"""
    rows = (
        (
            await session.execute(
                select(PluginRegistryEntry).where(
                    PluginRegistryEntry.enabled.is_(True)
                )
            )
        )
        .scalars()
        .all()
    )
    # 已装 plugin keys
    installed_keys: set[str] = {
        k
        for (k,) in (
            await session.execute(select(PluginInstance.plugin_key))
        ).all()
    }

    out: list[MarketplaceEntry] = []
    q_lower = (query or "").strip().lower()
    for r in rows:
        for entry in r.cached_entries or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name", "")
            description = entry.get("description", "")
            entry_tags = entry.get("tags") or []
            if q_lower and q_lower not in name.lower() and q_lower not in description.lower():
                continue
            if tag and tag not in entry_tags:
                continue
            out.append(
                MarketplaceEntry(
                    registry_id=r.id,
                    registry_name=r.name,
                    name=name,
                    latest=entry.get("latest", ""),
                    type=entry.get("type", ""),
                    description=description,
                    manifest_url=entry.get("manifest_url", ""),
                    signature_url=entry.get("signature_url", ""),
                    publisher=entry.get("publisher", ""),
                    tags=list(entry_tags),
                    downloads=int(entry.get("downloads") or 0),
                    updated_at=entry.get("updated_at", ""),
                    installed=name in installed_keys,
                )
            )
    return out


# ── install ───────────────────────────────────────────


async def install_from_remote(
    session: AsyncSession, req: InstallFromRemoteRequest
) -> dict:
    row = await _load_registry(session, req.registry_id)
    if not row.enabled:
        raise BusinessError(
            ResultCode.Fail,
            message=f"registry 已 disabled: {row.registry_url}",
        )
    # 从缓存挑 entry；找不到 → 提示先 sync
    matched: dict | None = None
    for entry in row.cached_entries or []:
        if isinstance(entry, dict) and entry.get("name") == req.plugin_name:
            matched = entry
            break
    if matched is None:
        raise BusinessError(
            ResultCode.NotFound,
            message=(
                f"在 registry {row.name!r} 找不到 plugin {req.plugin_name!r}；"
                "请先 sync"
            ),
        )

    # 拉 manifest + 验签
    remote_entry = RemotePluginEntry(
        name=matched["name"],
        latest=matched["latest"],
        type=matched["type"],
        description=matched.get("description", ""),
        manifest_url=matched["manifest_url"],
        signature_url=matched["signature_url"],
        publisher=matched["publisher"],
        tags=list(matched.get("tags") or []),
        downloads=int(matched.get("downloads") or 0),
        updated_at=matched.get("updated_at", ""),
        publisher_pubkey=matched["publisher_pubkey"],
    )
    try:
        manifest_dict = await fetch_and_verify_manifest(remote_entry)
    except RegistryClientError as e:
        raise BusinessError(ResultCode.Fail, message=str(e)) from e

    try:
        manifest = PluginManifest.model_validate(manifest_dict)
    except Exception as e:
        raise BusinessError(
            ResultCode.ValidationError,
            message=f"远端 manifest 校验失败: {e}",
        ) from e

    try:
        entry = await plugin_registry.install(
            session,
            manifest=manifest,
            source="marketplace",
            source_url=row.registry_url,
        )
    except ValueError as e:
        raise BusinessError(ResultCode.Fail, message=str(e)) from e

    return {
        "plugin_key": entry.plugin_key,
        "plugin_type": entry.plugin_type,
        "instance_id": entry.instance_id,
        "publisher": remote_entry.publisher,
        "registry": row.name,
    }


# ── helper ────────────────────────────────────────────


async def _load_registry(
    session: AsyncSession, registry_id: int
) -> PluginRegistryEntry:
    row = (
        await session.execute(
            select(PluginRegistryEntry).where(
                PluginRegistryEntry.id == registry_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.NotFound, message=f"registry 不存在: {registry_id}"
        )
    return row


# 防 lint：json 后续可能用到
_ = json
