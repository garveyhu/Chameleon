"""Builtin plugin manifest 列表

首次启动由 lifespan 调 PluginRegistry.bootstrap_builtin() seed 入库。
后续这三个 provider 即"内置插件"，admin 可 disable 但不可 uninstall。

未来其他 builtin（如 openai/anthropic 原生 provider）也在这里加一行。
"""

from __future__ import annotations

from typing import Any

BUILTIN_PROVIDERS: list[dict[str, Any]] = [
    {
        "manifest": {
            "name": "local",
            "version": "1.0.0",
            "type": "provider",
            "entrypoint": "chameleon.providers.local:PROVIDER",
            "chameleon_version": ">=0.5",
            "description": "本地 in-process provider，调 BaseAgent 子类",
        },
    },
    {
        "manifest": {
            "name": "dify",
            "version": "1.0.0",
            "type": "provider",
            "entrypoint": "chameleon.providers.dify:PROVIDER",
            "chameleon_version": ">=0.5",
            "description": "Dify API 接入 provider",
            "permissions": {"network": True},
        },
    },
    {
        "manifest": {
            "name": "fastgpt",
            "version": "1.0.0",
            "type": "provider",
            "entrypoint": "chameleon.providers.fastgpt:PROVIDER",
            "chameleon_version": ">=0.5",
            "description": "FastGPT API 接入 provider",
            "permissions": {"network": True},
        },
    },
]
