"""Plugin 实现层：进程内 registry + builtin 列表。

协议 / 数据（PluginManifest / ManifestPermissions / PluginType …）在
chameleon.core.plugins.manifest，SDK 装饰器在 chameleon.core.plugins.sdk。

registry_client / signing 走深 import：
    from chameleon.integrations.plugins.signing import verify_manifest
    from chameleon.integrations.plugins.registry_client import fetch_index
"""

from chameleon.integrations.plugins.builtins import BUILTIN_PROVIDERS
from chameleon.integrations.plugins.registry import (
    PluginEntry,
    PluginRegistry,
    assert_entrypoint_not_internal,
    plugin_registry,
)

__all__ = [
    "PluginRegistry",
    "PluginEntry",
    "plugin_registry",
    "assert_entrypoint_not_internal",
    "BUILTIN_PROVIDERS",
]
