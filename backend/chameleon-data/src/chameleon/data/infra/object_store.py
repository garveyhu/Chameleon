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
from typing import Any, BinaryIO
from urllib.parse import unquote, urlparse

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

    def presigned_put_url(
        self,
        key: str,
        *,
        expires_seconds: int = 600,
    ) -> str:
        """生成临时直传 URL —— 前端拿到后 PUT 上传

        P19.4 PR #41：多模态上传链路。前端拿 URL 后直传 MinIO，避免文件
        中转经过后端。expires 短一点（默认 10 min）足够前端发起 PUT。
        """
        self.ensure_bucket()
        return self._client.presigned_put_object(
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

    def refresh_url(
        self, url: str | None, *, expires_seconds: int = 7 * 24 * 3600
    ) -> str | None:
        """指向本 store（同 endpoint + bucket）的 URL → 提取 object key 重签新鲜
        presigned GET URL；其余（外链 / data: / emoji / 非本 store）原样返回。

        用途：把 presigned GET URL 当持久字段存的地方（ui_config 的 icon/bubble 图等），
        serve 时刷新一遍，避免 24h 后签名过期变裂图。key 取自路径段，与旧签名是否过期无关。
        """
        if not url or "://" not in url:
            return url
        parsed = urlparse(url)
        if parsed.netloc != self._endpoint:
            return url
        path = unquote(parsed.path).lstrip("/")
        prefix = f"{self._bucket}/"
        if not path.startswith(prefix):
            return url
        key = path[len(prefix) :]
        if not key:
            return url
        return self.presigned_get_url(key, expires_seconds=expires_seconds)


def get_object_store() -> ObjectStore:
    """获取全局 ObjectStore 单例。"""
    return ObjectStore()


def refresh_object_urls(obj: Any, *, expires_seconds: int = 7 * 24 * 3600) -> Any:
    """递归刷新嵌套结构（dict / list / str）里所有指向本 store 的 presigned URL。

    非本 store 的字符串原样透传，因此对 ui_config 这种混了颜色 / 文案 / emoji /
    对象存储 URL 的字典安全：只有真正指向 MinIO 的 URL 会被重签。
    """
    store = get_object_store()

    def _walk(v: Any) -> Any:
        if isinstance(v, str):
            return store.refresh_url(v, expires_seconds=expires_seconds)
        if isinstance(v, dict):
            return {k: _walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [_walk(x) for x in v]
        return v

    return _walk(obj)
