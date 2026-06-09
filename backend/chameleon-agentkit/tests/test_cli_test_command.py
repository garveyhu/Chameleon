"""`agentkit test`（_cmd_test）零配置 smoke 命令回归。

smoke 用 FakeTransport 把 agent 跑一遍：跑通且有产出 → exit 0；基本查询就崩 / 无产出 → exit 1。
作者写一个新 agent 后 `agentkit test my_pkg.agent` 立刻知道"至少不崩"——开发体验三件套之一。
"""

from __future__ import annotations

import sys
import types

from chameleon.agentkit import AgentRun, agent
from chameleon.agentkit._cli import _cmd_test


def _register(mod_name: str, key: str, handler) -> None:  # noqa: ANN001
    decorated = agent(key=key, name=key)(handler)
    decorated.__module__ = mod_name
    mod = types.ModuleType(mod_name)
    mod.handle = decorated  # type: ignore[attr-defined]
    sys.modules[mod_name] = mod


def test_smoke_passes_for_working_agent() -> None:
    async def handle(ctx: AgentRun):
        yield f"echo: {ctx.query}"

    _register("chameleon._t_cli.ok", "_t_cli_ok", handle)
    assert _cmd_test("chameleon._t_cli.ok", "你好") == 0


def test_smoke_fails_for_crashing_agent() -> None:
    async def handle(ctx: AgentRun):  # noqa: ARG001
        raise RuntimeError("基本查询就崩")
        yield ""  # pragma: no cover

    _register("chameleon._t_cli.crash", "_t_cli_crash", handle)
    assert _cmd_test("chameleon._t_cli.crash", "你好") == 1


def test_smoke_fails_for_empty_output_agent() -> None:
    async def handle(ctx: AgentRun):  # noqa: ARG001
        if False:  # 不产出任何 chunk
            yield ""

    _register("chameleon._t_cli.empty", "_t_cli_empty", handle)
    assert _cmd_test("chameleon._t_cli.empty", "你好") == 1
