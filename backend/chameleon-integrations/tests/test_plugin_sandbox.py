"""plugin entrypoint sandbox 静态检查（assert_entrypoint_not_internal）

实现随 registry 迁至 chameleon.integrations.plugins，故 sandbox 用例归这里；
SDK 装饰器用例仍在 chameleon-core/tests/test_plugin_sdk.py。
"""

from __future__ import annotations

import pytest

from chameleon.integrations.plugins import assert_entrypoint_not_internal


def test_sandbox_rejects_core_models():
    with pytest.raises(ValueError, match="内部模块沙箱"):
        assert_entrypoint_not_internal("chameleon.data.models.user:User")


def test_sandbox_rejects_core_infra():
    with pytest.raises(ValueError, match="内部模块沙箱"):
        assert_entrypoint_not_internal("chameleon.data.infra.db:engine")


def test_sandbox_rejects_system_layer():
    with pytest.raises(ValueError, match="内部模块沙箱"):
        assert_entrypoint_not_internal("chameleon.system.users.service:list_users")


def test_sandbox_rejects_api_layer():
    with pytest.raises(ValueError, match="内部模块沙箱"):
        assert_entrypoint_not_internal("chameleon.api.agent.api:router")


def test_sandbox_allows_provider_module():
    # 这是 builtin 用的路径，必须放过
    assert_entrypoint_not_internal("chameleon.providers.local:PROVIDER")


def test_sandbox_allows_external_package():
    assert_entrypoint_not_internal("my_plugin.provider:MyProvider")


def test_sandbox_allows_stdlib():
    # 测试常用 entrypoint：datetime:datetime
    assert_entrypoint_not_internal("datetime:datetime")
