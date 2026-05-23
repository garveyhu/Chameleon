"""P20.1 PR #47: CodeRunnerTool 接通 + ToolNode 调度

用 mock runtime 跑（不依赖 docker），验证：
- Tool layer：成功 / 非零退出 / timeout / stdout 截断 / runtime 缺失
- ToolNode 层：graph 调度链路 + ctx 携带
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from chameleon.core.sandbox import (
    SandboxRuntimeError,
    list_runtime_names,
    register_runtime,
)
from chameleon.core.sandbox.mock import MockSandboxRuntime
from chameleon.core.tools.builtins.code_runner import CodeRunnerTool
from chameleon.core.tools.base import ToolContext


@pytest_asyncio.fixture(autouse=True)
async def _ensure_mock_runtime():
    """确保 mock runtime 已注册（不依赖 lifespan）"""
    if "mock" not in list_runtime_names():
        register_runtime(MockSandboxRuntime())
    yield


# ── Tool layer ─────────────────────────────────────


async def test_code_runner_python_hello():
    tool = CodeRunnerTool({"runtime": "mock", "timeout_sec": 10})
    r = await tool.run(
        args={"code": "print('hi from tool')"},
        ctx=ToolContext(caller="test", related_id="0"),
    )
    assert r.ok is True
    assert r.data["exit_code"] == 0
    assert "hi from tool" in r.data["stdout"]
    assert r.data["timed_out"] is False
    assert r.meta.get("runtime") == "mock"


async def test_code_runner_user_code_failed_still_tool_ok():
    """用户代码非 0 退出：Tool 仍 ok=True（数据带 exit_code != 0）"""
    tool = CodeRunnerTool({"runtime": "mock", "timeout_sec": 10})
    r = await tool.run(
        args={"code": "import sys; sys.exit(2)"},
        ctx=ToolContext(caller="test", related_id="0"),
    )
    assert r.ok is True
    assert r.data["exit_code"] == 2
    assert r.meta.get("user_code_failed") is True


async def test_code_runner_timeout_marks_data():
    tool = CodeRunnerTool({"runtime": "mock", "timeout_sec": 1})
    r = await tool.run(
        args={"code": "import time; time.sleep(60)"},
        ctx=ToolContext(caller="test", related_id="0"),
    )
    assert r.ok is True
    assert r.data["timed_out"] is True


async def test_code_runner_stdout_truncated():
    tool = CodeRunnerTool(
        {"runtime": "mock", "timeout_sec": 10, "max_stdout_bytes": 5_000}
    )
    r = await tool.run(
        args={"code": "print('A' * 100_000)"},
        ctx=ToolContext(caller="test", related_id="0"),
    )
    assert r.ok is True
    assert r.data["stdout_truncated"] is True
    assert len(r.data["stdout"]) <= 5_000


async def test_code_runner_empty_code_rejected():
    tool = CodeRunnerTool({"runtime": "mock"})
    r = await tool.run(
        args={"code": ""},
        ctx=ToolContext(caller="test", related_id="0"),
    )
    assert r.ok is False
    assert "code 必填" in r.error


async def test_code_runner_unknown_runtime_rejected():
    tool = CodeRunnerTool({"runtime": "totally-not-here"})
    r = await tool.run(
        args={"code": "print(1)"},
        ctx=ToolContext(caller="test", related_id="0"),
    )
    assert r.ok is False
    assert "未知" in r.error or "不可用" in r.error


async def test_code_runner_bad_config_rejected():
    tool = CodeRunnerTool({"runtime": "mock", "timeout_sec": 0})
    r = await tool.run(
        args={"code": "print(1)"},
        ctx=ToolContext(caller="test", related_id="0"),
    )
    assert r.ok is False
    assert "config" in r.error or "timeout" in r.error


async def test_code_runner_stdin_passthrough():
    tool = CodeRunnerTool({"runtime": "mock", "timeout_sec": 10})
    r = await tool.run(
        args={
            "code": "import sys; print(sys.stdin.read().upper())",
            "stdin": "abc",
        },
        ctx=ToolContext(caller="test", related_id="0"),
    )
    assert r.ok is True
    assert "ABC" in r.data["stdout"]


# ── ToolNode graph 调度 ─────────────────────────────


async def test_tool_node_dispatches_code_runner():
    """通过 GraphExecutor 路径调 CodeRunnerTool，验证 ctx 串得通"""
    from datetime import datetime, timezone

    from chameleon.core.graph.context import NodeContext
    from chameleon.core.graph.executor import GraphExecutor
    from chameleon.core.graph.types import EdgeSpec, GraphSpec, NodeSpec

    spec = GraphSpec(
        nodes=[
            NodeSpec(id="start", type="start"),
            NodeSpec(
                id="code",
                type="tool",
                data={
                    "tool_key": "code-runner",
                    "args": {"code": "print('graph-' + 'ok')"},
                    "config": {"runtime": "mock", "timeout_sec": 10},
                },
            ),
            NodeSpec(id="end", type="end"),
        ],
        edges=[
            EdgeSpec(id="e1", source="start", target="code"),
            EdgeSpec(id="e2", source="code", target="end"),
        ],
    )

    executor = GraphExecutor(spec)
    ctx = NodeContext(
        request_id="t-code-sbx",
        graph_id=1,
        graph_run_id=1,
        started_at=datetime.now(timezone.utc),
    )
    result = await executor.run(input={}, ctx=ctx)

    assert result.status == "success", str(result.error)
    code_run = next(r for r in result.node_runs if r.node_id == "code")
    assert code_run.status == "success"
    assert "graph-ok" in code_run.output["data"]["stdout"]
