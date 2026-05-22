"""abilities DTO"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AbilityItem(BaseModel):
    """ability 出参 —— 含路由相关元信息 + 关联展示字段"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int | None = None
    model_code: str
    channel_id: int
    channel_name: str | None = None  # join 展示
    provider_code: str | None = None  # join 展示
    priority: int
    weight: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class CreateAbilityRequest(BaseModel):
    group_id: int | None = Field(
        default=None,
        description="NULL = 全局 ability，所有用户可路由",
    )
    model_code: str = Field(min_length=1, max_length=64)
    channel_id: int
    priority: int = Field(default=0, ge=0)
    weight: int = Field(default=0, ge=0)


class UpdateAbilityRequest(BaseModel):
    priority: int | None = Field(default=None, ge=0)
    weight: int | None = Field(default=None, ge=0)
    enabled: bool | None = None
