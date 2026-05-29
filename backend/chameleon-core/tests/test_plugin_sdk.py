"""P19.2 PR #34: plugin SDK 装饰器 + sandbox 静态检查"""

from __future__ import annotations

import pytest

from chameleon.core.plugins import (
    get_plugin_meta,
    plugin_embedding,
    plugin_provider,
    plugin_tool,
)
from chameleon.core.plugins.sdk import PluginMeta

# ── decorators 附加元数据 ───────────────────────────


def test_plugin_provider_decorator_attaches_meta():
    @plugin_provider(name="my-prov", version="1.2.0", description="demo")
    class MyProvider:
        pass

    meta = get_plugin_meta(MyProvider)
    assert isinstance(meta, PluginMeta)
    assert meta.name == "my-prov"
    assert meta.type == "provider"
    assert meta.description == "demo"


def test_plugin_tool_decorator():
    @plugin_tool(name="my-tool", version="0.1")
    class MyTool:
        pass

    assert get_plugin_meta(MyTool).type == "tool"


def test_plugin_embedding_decorator():
    @plugin_embedding(name="my-emb", version="0.1")
    class MyEmb:
        pass

    assert get_plugin_meta(MyEmb).type == "embedding"


def test_decorator_rejects_empty_name():
    with pytest.raises(ValueError, match="name"):

        @plugin_provider(name="", version="1.0")
        class _Bad:
            pass


def test_decorator_rejects_empty_version():
    with pytest.raises(ValueError, match="version"):

        @plugin_tool(name="x", version="")
        class _Bad:
            pass


def test_get_plugin_meta_returns_none_on_plain_class():
    class Plain:
        pass

    assert get_plugin_meta(Plain) is None
