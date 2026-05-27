"""app_templates DTO"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_CATEGORIES = ("assistant", "agent", "workflow", "rag")


class AppTemplateItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    category: str
    spec_json: dict[str, Any]
    cover_image: str | None = None
    verified: bool
    downloads: int
    created_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime


class CreateAppTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=4000)
    category: str = Field(min_length=1, max_length=32)
    spec_json: dict[str, Any]
    cover_image: str | None = Field(default=None, max_length=512)


class InstallTemplateResult(BaseModel):
    template_id: int
    template_name: str
    category: str
    installed_at: datetime
    # category 相关的产物 id（如 graph_id）；本 PR 占位返 None，留具体 dispatch
    artifact_id: int | None = None


CATEGORIES = _CATEGORIES
