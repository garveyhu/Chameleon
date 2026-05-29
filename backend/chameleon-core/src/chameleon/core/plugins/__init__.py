"""Plugin 协议 + SDK

仅导出纯协议 / 数据（manifest）与对外插件开发者 SDK（装饰器）。
registry / registry_client / signing / builtins 实现已迁至
chameleon.integrations.plugins。
"""

from chameleon.core.plugins.manifest import (
    ManifestConfigField,
    ManifestPermissions,
    PluginManifest,
    PluginSource,
    PluginType,
)
from chameleon.core.plugins.sdk import (
    PluginMeta,
    get_plugin_meta,
    plugin_embedding,
    plugin_provider,
    plugin_tool,
)

__all__ = [
    "PluginManifest",
    "ManifestPermissions",
    "ManifestConfigField",
    "PluginType",
    "PluginSource",
    "PluginMeta",
    "plugin_provider",
    "plugin_tool",
    "plugin_embedding",
    "get_plugin_meta",
]
