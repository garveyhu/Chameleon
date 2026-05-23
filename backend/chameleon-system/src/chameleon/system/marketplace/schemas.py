"""marketplace DTO"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RegistryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    registry_url: str
    name: str
    pubkey_pinning: dict[str, str] | None = None
    enabled: bool
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AddRegistryRequest(BaseModel):
    registry_url: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=128)


class UpdateRegistryRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    enabled: bool | None = None


class MarketplaceEntry(BaseModel):
    """搜索 / 浏览结果项 —— 已 flatten 出 registry_id"""

    registry_id: int
    registry_name: str
    name: str
    latest: str
    type: str
    description: str
    manifest_url: str
    signature_url: str
    publisher: str
    tags: list[str]
    downloads: int
    updated_at: str
    # 当前 plugin_instances 是否已装（按 plugin_key 比对）
    installed: bool = False


class InstallFromRemoteRequest(BaseModel):
    registry_id: int
    plugin_name: str


class SyncResult(BaseModel):
    registry_id: int
    entries: int
    publishers: int
    last_synced_at: datetime
