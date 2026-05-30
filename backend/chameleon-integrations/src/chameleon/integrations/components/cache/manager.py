"""CacheManager —— diskcache 单例（仿 sage cache_manager）

差异：
- sage 把业务表（PrefabSql 等）查询缓存逻辑写在 CacheManager 里——耦合业务
- chameleon 这里 CacheManager 是**通用 kv 缓存抽象**，业务方自己用 key
  约定（如 `kb:{kb_key}:meta`、`agent:{key}:metadata`）

用法：
    from chameleon.integrations.components import cache
    cache().set("my-key", value, expire=3600)
    v = cache().get("my-key", default=None)
    cache().delete("my-key")
"""

from __future__ import annotations

import threading
from typing import Any

from diskcache import Cache

from chameleon.core.config.constants import DATA_ROOT


class CacheManager:
    """全局 diskcache 单例（仿 sage CacheManager）"""

    _instance: CacheManager | None = None
    _lock = threading.Lock()

    def __new__(cls) -> CacheManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    cache_dir = DATA_ROOT / "diskcache"
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    inst._cache = Cache(str(cache_dir))
                    cls._instance = inst
        return cls._instance

    # ── KV API（薄封装；不暴露 diskcache 自己的 ABI） ───

    def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default=default)

    def set(
        self,
        key: str,
        value: Any,
        *,
        expire: float | None = None,
        tag: str | None = None,
    ) -> bool:
        return self._cache.set(key, value, expire=expire, tag=tag)

    def delete(self, key: str) -> bool:
        return self._cache.delete(key)

    def clear(self) -> int:
        return self._cache.clear()

    def evict_tag(self, tag: str) -> int:
        """按 tag 批量失效"""
        return self._cache.evict(tag)

    def __contains__(self, key: str) -> bool:
        return key in self._cache

    @property
    def raw(self) -> Cache:
        """逃生口：拿到底层 diskcache.Cache 做高级操作"""
        return self._cache


def cache() -> CacheManager:
    """顶层访问点（与 sage components/inventory 的 cache() 命名一致）"""
    return CacheManager()
