"""agentkit new 脚手架单测：渲染 + 落盘 + 生成的 @agent 可被 import/声明（T3-2）。"""

from __future__ import annotations

import importlib
import sys

import pytest

from chameleon.agentkit._scaffold import render_files, write_scaffold


def test_render_files_slug_and_content():
    files = render_files("Weather Bot!")  # 含空格/符号 → 规整
    paths = set(files)
    assert "weather-bot/pyproject.toml" in paths
    assert "weather-bot/src/chameleon/agents/weather_bot/agent.py" in paths
    assert "weather-bot/src/chameleon/agents/weather_bot/__init__.py" in paths
    agent_py = files["weather-bot/src/chameleon/agents/weather_bot/agent.py"]
    assert 'key="weather-bot"' in agent_py and "async def handle(ctx: AgentRun)" in agent_py
    pyproject = files["weather-bot/pyproject.toml"]
    assert 'weather-bot = "chameleon.agents.weather_bot"' in pyproject


def test_render_rejects_empty():
    with pytest.raises(ValueError):
        render_files("!!!")


def test_write_scaffold_creates_importable_agent(tmp_path):
    root = write_scaffold("demo-scaffold", tmp_path)
    assert root.exists()
    assert (root / "pyproject.toml").exists()
    # 不覆盖已存在
    with pytest.raises(FileExistsError):
        write_scaffold("demo-scaffold", tmp_path)

    # 生成的包可 import → @agent 声明生效（把 src 加进 path）
    src = str(root / "src")
    sys.path.insert(0, src)
    try:
        mod = importlib.import_module("chameleon.agents.demo_scaffold.agent")
        man = mod.handle.__agent_manifest__
        assert man.key == "demo-scaffold"
        assert [s.name for s in man.models] == ["chat"]
    finally:
        sys.path.remove(src)
        for m in list(sys.modules):
            if m.startswith("chameleon.agents.demo_scaffold"):
                del sys.modules[m]
