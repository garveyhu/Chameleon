"""Plugin Manifest 协议 —— P19.2 PR #33

外部插件根目录放 `manifest.toml`（或等价 JSON），结构：

```toml
[plugin]
name = "openrouter-provider"
version = "1.0.0"
type = "provider"  # provider | tool | embedding
entrypoint = "openrouter_provider.provider:OpenRouterProvider"
chameleon_version = ">=0.5.0"

[plugin.permissions]
network = true
filesystem = false

[plugin.config_schema.api_key]
type = "string"
required = true
sensitive = true
```

红线（plan §2 新增）：
- ⛔ manifest 不允许包含可执行代码 —— 只声明 entrypoint 字符串路径
- ⛔ entrypoint 必须是 `pkg.module:Symbol` 格式，禁止动态 import("__import__") 等
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PluginType = Literal["provider", "tool", "embedding"]
PluginSource = Literal["builtin", "local", "git", "pypi"]


_ENTRYPOINT_RE = re.compile(r"^[a-zA-Z_][\w\.]*:[a-zA-Z_]\w*$")
_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\-]{0,63}$")
_VERSION_RE = re.compile(r"^\d+\.\d+(\.\d+)?([\-\+][\w\.]+)?$")
_COMPAT_RE = re.compile(r"^(>=|<=|==|>|<|~=)?\d+\.\d+(\.\d+)?$")


class ManifestPermissions(BaseModel):
    """声明性权限 —— 当前仅作为元数据展示，未来 sandbox enforce 用"""

    model_config = ConfigDict(extra="forbid")

    network: bool = False
    filesystem: bool = False


class ManifestConfigField(BaseModel):
    """plugin 用户配置 schema 的一项"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["string", "int", "float", "bool"] = "string"
    required: bool = False
    sensitive: bool = False
    default: Any | None = None
    description: str | None = None
    enum: list[Any] | None = None


class PluginManifest(BaseModel):
    """plugin 元数据 + 入口 —— 入库后即 plugin_instances.manifest"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=32)
    type: PluginType
    entrypoint: str = Field(min_length=3, max_length=256)
    chameleon_version: str = Field(default=">=0.5", max_length=32)
    description: str | None = Field(default=None, max_length=500)
    config_schema: dict[str, ManifestConfigField] = Field(default_factory=dict)
    permissions: ManifestPermissions = Field(default_factory=ManifestPermissions)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError(
                "name 必须以字母开头，仅含字母/数字/下划线/连字符"
            )
        return v

    @field_validator("version")
    @classmethod
    def _validate_version(cls, v: str) -> str:
        if not _VERSION_RE.match(v):
            raise ValueError(
                "version 必须形如 1.2 / 1.2.3 / 1.2.3-rc.1"
            )
        return v

    @field_validator("entrypoint")
    @classmethod
    def _validate_entrypoint(cls, v: str) -> str:
        if not _ENTRYPOINT_RE.match(v):
            raise ValueError(
                "entrypoint 必须形如 `pkg.module:Symbol`，"
                "禁止动态导入 / 反射调用语法"
            )
        # 双保险：彻底拒绝可执行片段（虽然 regex 已挡掉，但被 import 副作用绕开很糟）
        forbidden = ("__import__", "eval(", "exec(", "compile(", "subprocess")
        for kw in forbidden:
            if kw in v:
                raise ValueError(
                    f"entrypoint 含敏感关键字 {kw!r}：禁止"
                )
        return v

    @field_validator("chameleon_version")
    @classmethod
    def _validate_compat(cls, v: str) -> str:
        if not _COMPAT_RE.match(v):
            raise ValueError(
                "chameleon_version 必须形如 >=0.5 / ==0.5.0 / ~=0.5"
            )
        return v

    def parse_entrypoint(self) -> tuple[str, str]:
        """`pkg.mod:Symbol` → ("pkg.mod", "Symbol")"""
        module_path, _, symbol = self.entrypoint.partition(":")
        return module_path, symbol
