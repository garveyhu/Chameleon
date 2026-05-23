"""tools DTO"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolInstanceItem(BaseModel):
    """tool_instances 出参"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tool_key: str
    name: str
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool
    created_at: datetime
    updated_at: datetime


class CreateToolInstanceRequest(BaseModel):
    tool_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateToolInstanceRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class ToolCatalogItem(BaseModel):
    """已注册的内置 Tool 元信息（admin 选 tool_key 时用）"""

    tool_key: str
    description: str
    parameters_schema: dict[str, Any]
    default_enabled: bool
    instance_id: int | None = None
    instance_enabled: bool | None = None
