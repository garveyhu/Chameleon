"""files API DTO"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# 红线（plan §2 新增）：image/audio 走 URL 不内嵌 base64；这里限 mime + size
ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        # image
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
        # audio
        "audio/mp3",
        "audio/mpeg",
        "audio/wav",
        "audio/x-wav",
        "audio/ogg",
        "audio/webm",
        # 通用（前端可显式声明文档类型；不在白名单则 400）
        "application/pdf",
    }
)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


class PresignedUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=256)
    content_type: str = Field(min_length=1, max_length=128)
    size: int = Field(ge=1, le=MAX_UPLOAD_BYTES)
    # 可选：业务方分组（如 'multimodal/chat'、'kb/upload'）
    namespace: str = Field(
        default="multimodal",
        max_length=64,
        pattern=r"^[a-zA-Z0-9_\-/]+$",
    )


class PresignedUploadResult(BaseModel):
    """前端拿到这个 → PUT upload_url（不带额外 header）→ finalize"""

    object_id: str  # 内部 object key（含 namespace 前缀）
    upload_url: str  # presigned PUT
    object_url: str  # presigned GET（短期 + 直接给 ContentBlock 用）
    expires_in: int  # GET URL 有效秒数
    max_bytes: int


class FinalizeRequest(BaseModel):
    """finalize 时上报实际写入字节数 / 校验元数据；后端 stat 一次确认"""

    expected_size: int | None = None


class FinalizeResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    object_id: str
    size: int
    content_type: str | None = None
    etag: str | None = None
    object_url: str  # 长效 presigned GET（供 ContentBlock 引用）
