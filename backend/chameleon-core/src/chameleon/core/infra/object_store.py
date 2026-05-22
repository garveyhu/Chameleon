"""MinIO object-store 单例

约定：
- 端点 / bucket / 凭据全走 inventory.minio_config()
- bucket 缺失时启动 ensure 创建（lifespan 钩用）
- 不暴露原始 minio.Minio 客户端的复杂 ABI，对业务方只露常用 put / get / delete / presigned

KB 文档约定 object key：`kb_uploads/{kb_id}/{doc_id}.bin`
"""

from __future__ import annotations

import io
import threading
from datetime import timedelta
from typing import BinaryIO

from loguru import logger
from minio import Minio
from minio.error import S3Error

from chameleon.core.config import inventory


class ObjectStore:
    """MinIO 单例 + bucket 自动初始化"""

    _instance: "ObjectStore | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        cfg = inventory.minio_config()
        self._endpoint = cfg["endpoint"]
        self._secure = bool(cfg["secure"])
        self._bucket = cfg["bucket"]
        self._public_url = cfg["public_url"].rstrip("/")
        access_key = cfg.get("access_key") or ""
        secret_key = cfg.get("secret_key") or ""
        if not access_key or not secret_key:
            raise RuntimeError(
                "minio access_key / secret_key 未配置（设 MINIO_ACCESS_KEY / MINIO_SECRET_KEY）"
            )
        self._client = Minio(
            endpoint=self._endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=self._secure,
        )
        self._bucket_ready = False

    def __new__(cls) -> "ObjectStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    # ── bucket lifecycle ────────────────────────────────────

    def ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                logger.info("[minio] bucket created: {}", self._bucket)
            else:
                logger.info("[minio] bucket ready: {}", self._bucket)
            self._bucket_ready = True
        except S3Error:
            logger.exception("[minio] ensure_bucket failed: {}", self._bucket)
            raise

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def public_url(self) -> str:
        return self._public_url

    # ── object 操作 ─────────────────────────────────────────

    def put(
        self,
        key: str,
        content: bytes,
        *,
        content_type: str | None = None,
    ) -> int:
        """写入字节，返写入大小。"""
        self.ensure_bucket()
        stream: BinaryIO = io.BytesIO(content)
        self._client.put_object(
            bucket_name=self._bucket,
            object_name=key,
            data=stream,
            length=len(content),
            content_type=content_type or "application/octet-stream",
        )
        return len(content)

    def get(self, key: str) -> bytes:
        """取整对象字节。"""
        resp = self._client.get_object(self._bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def delete(self, key: str) -> None:
        """删除对象（幂等，不存在不报错）。"""
        try:
            self._client.remove_object(self._bucket, key)
        except S3Error as e:
            if e.code in ("NoSuchKey", "NoSuchObject"):
                return
            raise

    def presigned_get_url(self, key: str, *, expires_seconds: int = 3600) -> str:
        """生成临时下载 URL"""
        return self._client.presigned_get_object(
            self._bucket, key, expires=timedelta(seconds=expires_seconds)
        )

    def stat(self, key: str) -> dict:
        """返对象大小 / mime / etag"""
        info = self._client.stat_object(self._bucket, key)
        return {
            "size": info.size,
            "content_type": info.content_type,
            "etag": info.etag,
            "last_modified": info.last_modified,
        }


def get_object_store() -> ObjectStore:
    """获取全局 ObjectStore 单例。"""
    return ObjectStore()
