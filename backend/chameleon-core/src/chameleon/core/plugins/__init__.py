"""Plugin 协议 + 注册表 —— P19.2

孵化外部 provider / tool / embedding 扩展。PR #33 落 manifest 协议、ORM、
PluginRegistry 骨架；hot reload (admin enable/disable 不重启) + builtin seed 也在本 PR。
"""

from chameleon.core.plugins.manifest import (
    PluginManifest,
    ManifestPermissions,
    ManifestConfigField,
    PluginType,
    PluginSource,
)
from chameleon.core.plugins.registry import (
    PluginRegistry,
    PluginEntry,
    plugin_registry,
    assert_entrypoint_not_internal,
)
from chameleon.core.plugins.sdk import (
    PluginMeta,
    plugin_provider,
    plugin_tool,
    plugin_embedding,
    get_plugin_meta,
)

__all__ = [
    "PluginManifest",
    "ManifestPermissions",
    "ManifestConfigField",
    "PluginType",
    "PluginSource",
    "PluginRegistry",
    "PluginEntry",
    "plugin_registry",
    "assert_entrypoint_not_internal",
    "PluginMeta",
    "plugin_provider",
    "plugin_tool",
    "plugin_embedding",
    "get_plugin_meta",
]
