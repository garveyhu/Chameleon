"""KB 上传文件本地存储

约定 source_uri 形如 "kb_uploads/{kb_id}/{doc_id}.bin"（相对 DATA_ROOT）。
"""

from __future__ import annotations

from pathlib import Path

from chameleon.core.config.constants import DATA_ROOT

UPLOAD_ROOT = DATA_ROOT / "kb_uploads"


def upload_path(kb_id: int, doc_id: int) -> Path:
    return UPLOAD_ROOT / str(kb_id) / f"{doc_id}.bin"


def relative_source_uri(kb_id: int, doc_id: int) -> str:
    return f"kb_uploads/{kb_id}/{doc_id}.bin"


def write_upload(kb_id: int, doc_id: int, content: bytes) -> tuple[str, int]:
    """落盘上传字节，返 (相对 source_uri, size_bytes)"""
    path = upload_path(kb_id, doc_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return relative_source_uri(kb_id, doc_id), len(content)


def read_upload(source_uri: str) -> bytes:
    """source_uri 是相对 DATA_ROOT 的路径"""
    path = DATA_ROOT / source_uri
    return path.read_bytes()


def delete_upload(source_uri: str) -> None:
    path = DATA_ROOT / source_uri
    if path.exists():
        path.unlink()
