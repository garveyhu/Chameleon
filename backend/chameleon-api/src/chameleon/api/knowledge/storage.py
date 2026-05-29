"""KB 文档原文存储（MinIO 对象存储后端）

object key 约定："kb_uploads/{kb_id}/{doc_id}.bin"
存进 document.source_uri，worker 读时按 key 直拉。
"""

from __future__ import annotations

from chameleon.data.infra.object_store import get_object_store


def object_key(kb_id: int, doc_id: int) -> str:
    return f"kb_uploads/{kb_id}/{doc_id}.bin"


def write_upload(
    kb_id: int,
    doc_id: int,
    content: bytes,
    *,
    content_type: str | None = None,
) -> tuple[str, int]:
    """写入对象存储，返 (object_key, size_bytes)。size_bytes 与字节数一致。"""
    key = object_key(kb_id, doc_id)
    size = get_object_store().put(key, content, content_type=content_type)
    return key, size


def read_upload(source_uri: str) -> bytes:
    """source_uri 是 object key（不带 bucket 前缀）。"""
    return get_object_store().get(source_uri)


def delete_upload(source_uri: str) -> None:
    get_object_store().delete(source_uri)


def presigned_url(source_uri: str, *, expires_seconds: int = 3600) -> str:
    return get_object_store().presigned_get_url(
        source_uri, expires_seconds=expires_seconds
    )
