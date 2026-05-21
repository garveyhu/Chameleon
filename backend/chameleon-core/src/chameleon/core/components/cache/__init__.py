"""cache 子模块 —— diskcache 单例（吸收 sage CacheManager 习惯）"""

from chameleon.core.components.cache.manager import CacheManager, cache

__all__ = ["CacheManager", "cache"]
