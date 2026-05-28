"""files API DTO"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# 红线（plan §2）：image/audio 走 URL 不内嵌 base64；这里限 mime + size。
# 列表对齐 Dify Web App 默认可上传集合 —— 图 / 音 / 视 / 文档 全套。
# 浏览器对 .md / .svg / .epub 的 file.type 经常为空 → 二次校验在 _normalize_mime()
# 里按扩展名兜底。
ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        # ── 图像 ─────────────────────────────────────────────
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
        "image/svg+xml",
        "image/bmp",
        "image/tiff",
        # ── 音频 ─────────────────────────────────────────────
        "audio/mp3",
        "audio/mpeg",
        "audio/wav",
        "audio/x-wav",
        "audio/ogg",
        "audio/webm",
        "audio/mp4",
        "audio/x-m4a",
        "audio/amr",
        "audio/flac",
        # ── 视频（仅上传 + 引用，目前模型不直读，作业务方留存）─────
        "video/mp4",
        "video/quicktime",
        "video/webm",
        "video/x-msvideo",
        "video/mpeg",
        # ── PDF / Office / 富文本 ────────────────────────────
        "application/pdf",
        "application/msword",  # .doc
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
        "application/vnd.ms-excel",  # .xls
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
        "application/vnd.ms-powerpoint",  # .ppt
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
        "application/epub+zip",
        "application/rtf",
        "application/xml",
        "application/zip",  # 压缩包占位（接入方需自行解压）
        "application/json",
        # ── 纯文本族（含 Markdown / CSV / 代码片段） ─────────
        "text/plain",
        "text/markdown",
        "text/x-markdown",
        "text/html",
        "application/xhtml+xml",
        "text/csv",
        "application/csv",
        "text/xml",
        # 邮件
        "message/rfc822",
        "application/vnd.ms-outlook",
        # 通用兜底（mime 缺失时由 _normalize_mime 按扩展名映射上面具体类型）
        "application/octet-stream",
    }
)

# 扩展名 → 规范 mime；浏览器对 .md / .svg / 等送出 file.type='' 时按此兜底
EXT_TO_MIME: dict[str, str] = {
    "md": "text/markdown",
    "markdown": "text/markdown",
    "mdx": "text/markdown",
    "txt": "text/plain",
    "log": "text/plain",
    "csv": "text/csv",
    "html": "text/html",
    "htm": "text/html",
    "xml": "application/xml",
    "json": "application/json",
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "epub": "application/epub+zip",
    "rtf": "application/rtf",
    "zip": "application/zip",
    "eml": "message/rfc822",
    "msg": "application/vnd.ms-outlook",
    "svg": "image/svg+xml",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "m4a": "audio/x-m4a",
    "amr": "audio/amr",
    "flac": "audio/flac",
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "webm": "video/webm",
    "avi": "video/x-msvideo",
    "mpeg": "video/mpeg",
    "mpg": "video/mpeg",
}


def normalize_mime(filename: str, content_type: str) -> str:
    """mime 二次校验：浏览器对 .md/.svg 经常返空或 octet-stream，按文件扩展名兜底。"""
    mt = (content_type or "").lower().strip()
    if mt and mt != "application/octet-stream":
        return mt
    if "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in EXT_TO_MIME:
            return EXT_TO_MIME[ext]
    return mt or "application/octet-stream"

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
