"""plugins DTO"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PluginInstanceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plugin_key: str
    name: str
    type: str
    version: str
    source: str
    source_url: str | None = None
    manifest: dict[str, Any]
    config: dict[str, Any]
    enabled: bool
    installed_at: datetime
    updated_at: datetime


class InstallPluginRequest(BaseModel):
    """admin 安装插件 —— PR #34 仅接受 manifest 字典 + source 元信息

    tar.gz 上传 / git clone 留 PR #35（包管理需要 pip / sandbox）；当前请求方需
    保证插件包已通过 pip / namespace 加载到 venv，install 端只做注册。
    """

    manifest: dict[str, Any]
    source: str = Field(default="local", pattern=r"^(local|git|pypi)$")
    source_url: str | None = Field(default=None, max_length=512)
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateConfigRequest(BaseModel):
    config: dict[str, Any]


class PluginActionResult(BaseModel):
    """enable / disable / reload 结果统一壳"""

    plugin_key: str
    enabled: bool
    loaded: bool
    message: str | None = None
