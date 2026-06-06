"""产物落 MinIO —— 各驱动共享的产物持久化。

上游产物可能是即时 url（DashScope 24h 过期）或字节流（ComfyUI /view），
统一下载/接收为字节后落 MinIO，对外返回长效 presigned url。
"""

from __future__ import annotations

import asyncio

from chameleon.data.infra.object_store import get_object_store

_CONTENT_TYPE = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "mp4": "video/mp4",
    "webm": "video/webm",
    "mov": "video/quicktime",
}


def content_type_for(filename: str, default: str = "application/octet-stream") -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _CONTENT_TYPE.get(ext, default)


async def store_media(
    data: bytes, *, ref: str, filename: str, content_type: str
) -> tuple[str, str]:
    """把产物字节落 MinIO，返回 (object_key, presigned_url)。

    Args:
        ref: 任务标识（prompt_id / task_id），用于 key 分目录
        filename: 产物文件名
        content_type: MIME
    """
    key = f"mediagen/{ref}/{filename}"
    store = get_object_store()
    await asyncio.to_thread(store.put, key, data, content_type=content_type)
    # 7 天 presigned（嵌进消息内容）；过期后由消息读取层 refresh_url 重签
    return key, store.presigned_get_url(key, expires_seconds=7 * 24 * 3600)
