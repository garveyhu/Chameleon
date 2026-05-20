"""BaseSettings —— 学 sage 的弱类型 JSON 配置基类

- 点路径 get/set（`get("database.mysql.host")`）
- from_json / from_yaml / from_env 类方法
- 占位符替换：`${env:NAME}`、`${baseurl:KEY}` 等，递归遍历所有 string value
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

import yaml

_PLACEHOLDER_RE = re.compile(
    r"\$\{(?P<scheme>[a-zA-Z_][a-zA-Z0-9_-]*):(?P<key>[^}]+)\}"
)


class ConfigError(Exception):
    """配置加载或解析错误"""


PlaceholderResolver = Callable[[str, str], str]
"""签名 (scheme, key) -> value；找不到时抛 ConfigError"""


class BaseSettings:
    """点路径访问的配置容器"""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data: dict[str, Any] = {} if data is None else data

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        result: Any = self.data
        for k in keys:
            if not isinstance(result, dict):
                return default
            if k not in result:
                return default
            result = result[k]
        return result

    def set(self, key: str, value: Any) -> None:
        keys = key.split(".")
        current: dict[str, Any] = self.data
        for k in keys[:-1]:
            current = current.setdefault(k, {})
        current[keys[-1]] = value

    def to_dict(self) -> dict[str, Any]:
        return self.data

    # ── 加载 ─────────────────────────────────────────────

    @classmethod
    def from_json(
        cls,
        path: Path,
        resolver: PlaceholderResolver | None = None,
    ) -> BaseSettings:
        if not path.exists():
            raise ConfigError(f"config file not found: {path}")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if resolver is not None:
            data = _resolve_placeholders(data, resolver)
        return cls(data)

    @classmethod
    def from_yaml(
        cls,
        path: Path,
        resolver: PlaceholderResolver | None = None,
    ) -> BaseSettings:
        if not path.exists():
            raise ConfigError(f"config file not found: {path}")
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if resolver is not None:
            data = _resolve_placeholders(data, resolver)
        return cls(data)


# ── 占位符递归替换 ────────────────────────────────────────


def _resolve_placeholders(data: Any, resolver: PlaceholderResolver) -> Any:
    if isinstance(data, dict):
        return {k: _resolve_placeholders(v, resolver) for k, v in data.items()}
    if isinstance(data, list):
        return [_resolve_placeholders(v, resolver) for v in data]
    if isinstance(data, str):
        return _PLACEHOLDER_RE.sub(
            lambda m: resolver(m.group("scheme"), m.group("key")),
            data,
        )
    return data


def make_default_resolver(
    baseurl_lookup: Callable[[str], str | None] | None = None,
) -> PlaceholderResolver:
    """构造默认 resolver，支持 ${env:NAME} 和 ${baseurl:KEY}

    fail-fast：找不到 → ConfigError
    """

    def resolve(scheme: str, key: str) -> str:
        if scheme == "env":
            value = os.environ.get(key)
            if value is None:
                raise ConfigError(f"env var not set: {key}")
            return value
        if scheme == "baseurl":
            if baseurl_lookup is None:
                raise ConfigError(
                    f"${{baseurl:{key}}} used but baseurl_lookup not provided"
                )
            value = baseurl_lookup(key)
            if value is None:
                raise ConfigError(f"baseurl key not found: {key}")
            return value
        raise ConfigError(f"unknown placeholder scheme: {scheme}")

    return resolve
