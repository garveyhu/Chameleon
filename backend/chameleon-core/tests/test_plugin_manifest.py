"""P19.2 PR #33: Plugin Manifest 协议校验"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from chameleon.core.plugins.manifest import (
    ManifestConfigField,
    ManifestPermissions,
    PluginManifest,
)

# ── 基本接受 ────────────────────────────────────────


def test_manifest_minimum_valid():
    m = PluginManifest(
        name="my-plugin",
        version="1.0.0",
        type="provider",
        entrypoint="my_pkg.provider:MyProvider",
    )
    assert m.name == "my-plugin"
    assert m.permissions.network is False
    assert m.permissions.filesystem is False
    assert m.config_schema == {}


def test_manifest_with_config_schema_and_permissions():
    m = PluginManifest(
        name="api-tool",
        version="2.1.0",
        type="tool",
        entrypoint="api_tool.main:Tool",
        chameleon_version=">=0.5",
        description="HTTP API 调用",
        config_schema={
            "api_key": ManifestConfigField(
                type="string", required=True, sensitive=True
            )
        },
        permissions=ManifestPermissions(network=True),
    )
    assert m.config_schema["api_key"].sensitive is True
    assert m.permissions.network is True


def test_parse_entrypoint():
    m = PluginManifest(
        name="x",
        version="0.1",
        type="tool",
        entrypoint="my_pkg.sub.mod:Symbol",
    )
    module_path, symbol = m.parse_entrypoint()
    assert module_path == "my_pkg.sub.mod"
    assert symbol == "Symbol"


# ── 名称 / 版本 / entrypoint 拒绝路径 ────────────────


def test_name_rejects_starting_digit():
    with pytest.raises(ValidationError):
        PluginManifest(
            name="1plugin",
            version="1.0.0",
            type="tool",
            entrypoint="x.y:Z",
        )


def test_name_rejects_invalid_char():
    with pytest.raises(ValidationError):
        PluginManifest(
            name="my plugin",  # 含空格
            version="1.0.0",
            type="tool",
            entrypoint="x.y:Z",
        )


def test_version_rejects_garbage():
    with pytest.raises(ValidationError):
        PluginManifest(
            name="x",
            version="latest",
            type="tool",
            entrypoint="x.y:Z",
        )


def test_entrypoint_must_be_pkg_colon_symbol():
    with pytest.raises(ValidationError):
        PluginManifest(
            name="x",
            version="1.0.0",
            type="tool",
            entrypoint="x.y.Z",  # 缺冒号
        )


def test_entrypoint_rejects_dynamic_import_keyword():
    """红线：禁止 __import__ / eval / exec 等关键字混入 entrypoint"""
    with pytest.raises(ValidationError):
        PluginManifest(
            name="x",
            version="1.0.0",
            type="tool",
            entrypoint="__import__:Foo",
        )


def test_compat_string_rejects_garbage():
    with pytest.raises(ValidationError):
        PluginManifest(
            name="x",
            version="1.0.0",
            type="tool",
            entrypoint="x.y:Z",
            chameleon_version="任意版本",
        )


# ── extra fields are forbidden（防 manifest 走私字段） ─────


def test_manifest_rejects_extra_fields():
    with pytest.raises(ValidationError):
        PluginManifest.model_validate(
            {
                "name": "x",
                "version": "1.0",
                "type": "tool",
                "entrypoint": "x.y:Z",
                "secret_field": "danger",  # extra
            }
        )


def test_permissions_rejects_extra_fields():
    with pytest.raises(ValidationError):
        ManifestPermissions.model_validate(
            {"network": True, "kernel": True}
        )
