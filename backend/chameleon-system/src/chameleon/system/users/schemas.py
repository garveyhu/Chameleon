"""users 模块 DTO"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserItem(BaseModel):
    """用户回显（list / detail 共用）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None = None
    display_name: str | None = None
    status: str
    locale: str
    must_change_password: bool
    last_login_at: datetime | None = None
    created_at: datetime
    role_codes: list[str] = Field(default_factory=list)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=255)
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, max_length=128)
    locale: str = "zh-CN"
    role_codes: list[str] = Field(default_factory=list)
    must_change_password: bool = True


class UpdateUserRequest(BaseModel):
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, max_length=128)
    locale: str | None = None
    status: str | None = Field(default=None, pattern="^(active|disabled)$")


class GrantRoleRequest(BaseModel):
    role_code: str


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=255)
    must_change_password: bool = True
