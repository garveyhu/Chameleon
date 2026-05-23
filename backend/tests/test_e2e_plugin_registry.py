"""P19.2 PR #33: PluginRegistry bootstrap + enable/disable + reload + install"""

from __future__ import annotations

import secrets

import pytest_asyncio
from sqlalchemy import delete, select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import PluginInstance
from chameleon.core.plugins import PluginRegistry
from chameleon.core.plugins.builtins import BUILTIN_PROVIDERS
from chameleon.core.plugins.manifest import PluginManifest


@pytest_asyncio.fixture(autouse=True)
async def _clean_plugins():
    """每个测试前后清表，互不污染"""
    async with AsyncSessionLocal() as s:
        await s.execute(delete(PluginInstance))
        await s.commit()
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(delete(PluginInstance))
        await s.commit()


# ── builtin seed ────────────────────────────────────────


async def test_bootstrap_builtin_seeds_three_providers():
    reg = PluginRegistry()
    async with AsyncSessionLocal() as s:
        added = await reg.bootstrap_builtin(s, BUILTIN_PROVIDERS)
        assert added == 3
        rows = (
            (await s.execute(select(PluginInstance).order_by(PluginInstance.plugin_key)))
            .scalars()
            .all()
        )
        keys = [r.plugin_key for r in rows]
        assert keys == ["dify", "fastgpt", "local"]
        assert all(r.source == "builtin" for r in rows)
        assert all(r.enabled for r in rows)


async def test_bootstrap_builtin_is_idempotent():
    reg = PluginRegistry()
    async with AsyncSessionLocal() as s:
        a1 = await reg.bootstrap_builtin(s, BUILTIN_PROVIDERS)
        a2 = await reg.bootstrap_builtin(s, BUILTIN_PROVIDERS)
        assert a1 == 3 and a2 == 0


# ── enable/disable + load_all ───────────────────────────


async def test_load_all_resolves_enabled_only():
    reg = PluginRegistry()
    async with AsyncSessionLocal() as s:
        await reg.bootstrap_builtin(s, BUILTIN_PROVIDERS)
        # disable dify
        await reg.set_enabled(s, "dify", False)
        entries = await reg.load_all(s)
    keys = {e.plugin_key for e in entries}
    assert "local" in keys
    assert "fastgpt" in keys
    assert "dify" not in keys


async def test_disabled_keys_for_type_returns_provider_disabled_set():
    reg = PluginRegistry()
    async with AsyncSessionLocal() as s:
        await reg.bootstrap_builtin(s, BUILTIN_PROVIDERS)
        await reg.set_enabled(s, "fastgpt", False)
        disabled = await reg.disabled_keys_for_type(s, "provider")
    assert disabled == {"fastgpt"}


async def test_set_enabled_reattaches_on_re_enable():
    reg = PluginRegistry()
    async with AsyncSessionLocal() as s:
        await reg.bootstrap_builtin(s, BUILTIN_PROVIDERS)
        await reg.load_all(s)
        assert reg.get("local") is not None

        await reg.set_enabled(s, "local", False)
        assert reg.get("local") is None

        await reg.set_enabled(s, "local", True)
        assert reg.get("local") is not None


# ── install / uninstall ─────────────────────────────────


async def test_install_loads_immediately_and_uninstall_clears_cache():
    """用 datetime 作为合法的 importable 入口（已在 stdlib，免新建 fixture 包）"""
    reg = PluginRegistry()
    manifest = PluginManifest(
        name=f"test-stdlib-{secrets.token_hex(2)}",
        version="1.0.0",
        type="tool",
        entrypoint="datetime:datetime",
    )
    async with AsyncSessionLocal() as s:
        entry = await reg.install(s, manifest=manifest, source="local")
        assert entry.plugin_key == manifest.name
        assert reg.get(manifest.name) is not None

        ok = await reg.uninstall(s, manifest.name)
        assert ok is True
        assert reg.get(manifest.name) is None


async def test_install_duplicate_rejected():
    reg = PluginRegistry()
    manifest = PluginManifest(
        name=f"test-dup-{secrets.token_hex(2)}",
        version="1.0.0",
        type="tool",
        entrypoint="datetime:datetime",
    )
    async with AsyncSessionLocal() as s:
        await reg.install(s, manifest=manifest)
        import pytest

        with pytest.raises(ValueError, match="已存在"):
            await reg.install(s, manifest=manifest)


async def test_uninstall_builtin_forbidden():
    reg = PluginRegistry()
    async with AsyncSessionLocal() as s:
        await reg.bootstrap_builtin(s, BUILTIN_PROVIDERS)
        import pytest

        with pytest.raises(ValueError, match="builtin"):
            await reg.uninstall(s, "local")


# ── reload ──────────────────────────────────────────────


async def test_reload_returns_fresh_entry():
    reg = PluginRegistry()
    manifest = PluginManifest(
        name=f"test-reload-{secrets.token_hex(2)}",
        version="1.0.0",
        type="tool",
        entrypoint="datetime:datetime",
    )
    async with AsyncSessionLocal() as s:
        await reg.install(s, manifest=manifest)
        first = reg.get(manifest.name)
        assert first is not None

        reloaded = await reg.reload(s, manifest.name)
        assert reloaded is not None
        assert reloaded.plugin_key == manifest.name


async def test_reload_disabled_returns_none():
    reg = PluginRegistry()
    manifest = PluginManifest(
        name=f"test-disabled-{secrets.token_hex(2)}",
        version="1.0.0",
        type="tool",
        entrypoint="datetime:datetime",
    )
    async with AsyncSessionLocal() as s:
        await reg.install(s, manifest=manifest)
        await reg.set_enabled(s, manifest.name, False)
        result = await reg.reload(s, manifest.name)
        assert result is None
        assert reg.get(manifest.name) is None
