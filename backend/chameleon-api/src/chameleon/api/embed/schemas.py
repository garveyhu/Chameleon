"""embed 模块 DTO + SessionPolicy（S10 重构）"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ── SessionPolicy（落 embed_configs.session_policy JSON）─────────────


class SessionPolicy(BaseModel):
    """嵌入式会话策略 —— 决定 widget 怎么管会话 / 终端用户怎么识别"""

    identification_mode: Literal[
        "anonymous_device", "external_user_id", "signed_jwt"
    ] = Field(
        default="anonymous_device",
        description="终端用户识别方式：浏览器匿名设备 / 接入方传外部 id / 签名 JWT",
    )
    # signed_jwt 模式用的 HS256 共享密钥（落库前会用 crypto.encrypt 加密；
    # 验签时 get_or_decrypt 解出来）。其他模式不需要。
    jwt_signing_secret_encrypted: str | None = None
    show_history_sidebar: bool = True
    auto_resume_last: bool = True
    allow_user_manage: bool = True
    max_history_days: int = Field(default=90, ge=1, le=365)

    model_config = ConfigDict(extra="ignore")


# ── 三种身份模式的入参 ───────────────────────────────────


class CreateSessionRequest(BaseModel):
    """POST /v1/embed/{embed_key}/session 入参 ——
    按 embed_config.session_policy.identification_mode 解析其一：
    - anonymous_device: 前端持久化的 device_id（uuid 等）→ hash 后当 end_user_id
    - external_user_id: 接入方直接传字符串
    - signed_jwt: 接入方签好的 JWT（HS256），sub claim 当 end_user_id
    """

    device_id: str | None = Field(None, min_length=8, max_length=128)
    external_user_id: str | None = Field(None, min_length=1, max_length=128)
    jwt_token: str | None = Field(None, max_length=4096)

    model_config = ConfigDict(extra="forbid")


# ── embed 会话管理 DTO ───────────────────────────────────


class EmbedSessionItem(BaseModel):
    """embed 端历史会话条目（仅暴露给已通过 origin/token 的 widget）"""

    session_id: str
    title: str | None
    last_message_at: str | None  # ISO8601 string
    created_at: str  # ISO8601 string


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class CreateNewSessionResponse(BaseModel):
    session_token: str
    session_id: str
    expires_in: int
