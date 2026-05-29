"""auth 模块 DTO"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ── 登录 / token ──────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=255)


class TokenPair(BaseModel):
    """登录 / refresh 成功响应"""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int  # access_token TTL 秒


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=255)


class FirstPasswordRequest(BaseModel):
    """首次登录改密（不需要旧密码 —— 已经用临时密码登入）"""

    new_password: str = Field(min_length=8, max_length=255)


# ── 当前用户回显 ──────────────────────────────────────────


class CurrentUserView(BaseModel):
    """/v1/auth/me 响应"""

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
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
