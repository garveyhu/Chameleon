"""workspace DTO"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_key: str
    name: str
    plan: str
    config: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class CreateWorkspaceRequest(BaseModel):
    workspace_key: str = Field(
        min_length=1, max_length=64, pattern=r"^[a-zA-Z][a-zA-Z0-9_\-]{0,63}$"
    )
    name: str = Field(min_length=1, max_length=128)
    plan: Literal["free", "pro", "enterprise"] = "free"
    config: dict[str, Any] | None = None


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    plan: Literal["free", "pro", "enterprise"] | None = None
    config: dict[str, Any] | None = None


class MemberItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    workspace_id: int
    team_id: int | None = None
    role: str
    created_at: datetime
    # 反查出来的展示字段
    username: str | None = None


class AddMemberRequest(BaseModel):
    user_id: int
    team_id: int | None = None
    role: Literal["owner", "admin", "member", "viewer"] = "member"


class UpdateMemberRoleRequest(BaseModel):
    role: Literal["owner", "admin", "member", "viewer"]


# ── quota ────────────────────────────────────────────


class QuotaItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: int
    token_quota_monthly: int | None = None
    token_used_current_month: int
    request_quota_daily: int | None = None
    request_used_today: int
    reset_at: datetime


class UpdateQuotaRequest(BaseModel):
    token_quota_monthly: int | None = Field(default=None, ge=0)
    request_quota_daily: int | None = Field(default=None, ge=0)
    # 显式重置 used 计数（管理员 force reset）
    reset_used: bool = False
