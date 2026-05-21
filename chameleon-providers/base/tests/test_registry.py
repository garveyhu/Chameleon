"""Registry 构建逻辑单测

不实际启动 provider/agent —— 用 monkeypatch 替换扫描结果。
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from chameleon.core.exceptions import RegistryError
from chameleon.providers.base.protocol import Provider
from chameleon.providers.base.registry import (
    _build_yaml_agents,
    build_agent_registry,
)
from chameleon.providers.base.types import InvokeContext, StreamEvent


class _FakeProvider(Provider):
    def __init__(self, name: str) -> None:
        self.name = name

    async def stream(self, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        if False:
            yield StreamEvent(type="done", data={})  # noqa
        raise NotImplementedError


def test_build_agent_registry_with_yaml_file(tmp_path: Path) -> None:
    yaml_path = tmp_path / "agents.yaml"
    yaml_path.write_text(
        "- key: faq\n"
        "  provider: dify\n"
        "  description: customer faq\n"
        "  endpoint: http://localhost/v1\n"
        "  app_id: app-x\n"
        "  api_key_env: TEST_KEY\n"
    )
    providers = {"dify": _FakeProvider("dify"), "local": _FakeProvider("local")}
    agents = build_agent_registry(providers, yaml_path=yaml_path)
    assert "faq" in agents
    assert agents["faq"].provider == "dify"
    assert agents["faq"].config["endpoint"] == "http://localhost/v1"


def test_yaml_agents_unknown_provider_fail_fast(tmp_path: Path) -> None:
    yaml_path = tmp_path / "agents.yaml"
    yaml_path.write_text("- key: x\n  provider: nonexistent\n  endpoint: http://x\n")
    providers = {"dify": _FakeProvider("dify"), "local": _FakeProvider("local")}
    with pytest.raises(RegistryError):
        build_agent_registry(providers, yaml_path=yaml_path)


def test_yaml_agents_placeholder_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_AGENT_APP_ID", "resolved-app-id")
    yaml_path = tmp_path / "agents.yaml"
    yaml_path.write_text(
        "- key: y\n"
        "  provider: dify\n"
        "  endpoint: http://localhost\n"
        "  app_id: ${env:TEST_AGENT_APP_ID}\n"
    )
    # 注：build_agent_registry 也扫 chameleon.agents.* namespace（含 echo, provider=langgraph）
    providers = {"dify": _FakeProvider("dify"), "local": _FakeProvider("local")}
    agents = build_agent_registry(providers, yaml_path=yaml_path)
    assert agents["y"].config["app_id"] == "resolved-app-id"


def test_yaml_agents_placeholder_missing_env_fail_fast(tmp_path: Path) -> None:
    yaml_path = tmp_path / "agents.yaml"
    yaml_path.write_text(
        "- key: z\n"
        "  provider: dify\n"
        "  endpoint: http://localhost\n"
        "  app_id: ${env:DEFINITELY_NOT_SET_VAR_XYZ}\n"
    )
    providers = {"dify": _FakeProvider("dify"), "local": _FakeProvider("local")}
    with pytest.raises(RegistryError):
        build_agent_registry(providers, yaml_path=yaml_path)


def test_yaml_empty_or_missing(tmp_path: Path) -> None:
    """文件不存在 / 空 / 显式空数组 都返 {}"""
    # 不存在
    assert _build_yaml_agents(tmp_path / "missing.yaml") == {}

    # 空
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    assert _build_yaml_agents(empty) == {}

    # 空数组
    empty_list = tmp_path / "empty-list.yaml"
    empty_list.write_text("[]\n")
    assert _build_yaml_agents(empty_list) == {}


def test_yaml_invalid_format_fail_fast(tmp_path: Path) -> None:
    yaml_path = tmp_path / "agents.yaml"
    yaml_path.write_text("not_a_list: true\n")
    with pytest.raises(RegistryError):
        _build_yaml_agents(yaml_path)
