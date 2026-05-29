"""P20.1 PR #45: SandboxRuntime 协议 + Mock 实现"""

from __future__ import annotations

import sys

import pytest

from chameleon.core.sandbox import (
    SandboxConfig,
    SandboxRuntime,
    SandboxRuntimeError,
    get_runtime,
    list_runtime_names,
    register_runtime,
)
from chameleon.core.sandbox.mock import MockSandboxRuntime
from chameleon.core.sandbox.runtime import is_production

# ── config 上下界校验 ────────────────────────────────────


def test_config_default_ok():
    c = SandboxConfig()
    assert c.language == "python"
    assert c.timeout_sec == 30.0
    assert c.network == "none"


def test_config_rejects_zero_timeout():
    with pytest.raises(ValueError, match="timeout_sec"):
        SandboxConfig(timeout_sec=0)


def test_config_rejects_huge_timeout():
    with pytest.raises(ValueError, match="timeout_sec"):
        SandboxConfig(timeout_sec=601)


def test_config_rejects_low_memory():
    with pytest.raises(ValueError, match="memory_mb"):
        SandboxConfig(memory_mb=16)


def test_config_rejects_high_cpu():
    with pytest.raises(ValueError, match="cpu_quota"):
        SandboxConfig(cpu_quota=5)


def test_config_rejects_network_full():
    """plan §2 P20：network='full' 暂禁用"""
    with pytest.raises(ValueError, match="暂禁用"):
        SandboxConfig(network="full")


# ── registry ─────────────────────────────────────────────


def test_register_and_get():
    rt = MockSandboxRuntime()
    register_runtime(rt)
    assert "mock" in list_runtime_names()
    assert get_runtime("mock") is rt


def test_get_unknown_raises():
    with pytest.raises(SandboxRuntimeError, match="未知"):
        get_runtime("totally-not-a-runtime")


def test_register_rejects_unnamed():
    class _Unnamed(SandboxRuntime):
        name = ""  # 故意留空

        async def execute(self, **kwargs):
            raise NotImplementedError

    with pytest.raises(ValueError, match="未设 name"):
        register_runtime(_Unnamed())


# ── 生产环境守卫 ───────────────────────────────────────


def test_mock_runtime_refuses_production(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CHAMELEON_ENV", "production")
    assert is_production() is True
    with pytest.raises(SandboxRuntimeError, match="生产"):
        MockSandboxRuntime()


def test_mock_runtime_allowed_in_dev(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CHAMELEON_ENV", raising=False)
    assert is_production() is False
    rt = MockSandboxRuntime()
    assert rt.name == "mock"


# ── Mock runtime 真跑（subprocess） ─────────────────────


async def test_mock_python_hello():
    rt = MockSandboxRuntime()
    result = await rt.execute(
        code="print('hello sandbox')",
        config=SandboxConfig(timeout_sec=10),
    )
    assert result.ok is True
    assert result.exit_code == 0
    assert "hello sandbox" in result.stdout
    assert result.timed_out is False


async def test_mock_python_exit_code_nonzero():
    rt = MockSandboxRuntime()
    result = await rt.execute(
        code="import sys; sys.exit(7)",
        config=SandboxConfig(timeout_sec=10),
    )
    assert result.ok is False
    assert result.exit_code == 7
    assert result.timed_out is False


async def test_mock_python_runtime_error_captured():
    rt = MockSandboxRuntime()
    result = await rt.execute(
        code="raise ValueError('boom')",
        config=SandboxConfig(timeout_sec=10),
    )
    assert result.exit_code != 0
    assert "ValueError" in result.stderr
    assert "boom" in result.stderr


async def test_mock_python_timeout_kills():
    rt = MockSandboxRuntime()
    result = await rt.execute(
        code="import time; time.sleep(60)",
        config=SandboxConfig(timeout_sec=1),
    )
    assert result.timed_out is True
    assert result.exit_code == -1
    assert result.duration_ms >= 1000


async def test_mock_python_stdout_truncated():
    rt = MockSandboxRuntime()
    # 输出 200KB 数据；max=10KB → 应截断
    code = "print('A' * 200_000)"
    result = await rt.execute(
        code=code,
        config=SandboxConfig(timeout_sec=10, max_stdout_bytes=10_000),
    )
    assert result.stdout_truncated is True
    assert len(result.stdout) <= 10_000


async def test_mock_python_stdin_passthrough():
    rt = MockSandboxRuntime()
    result = await rt.execute(
        code="import sys; print(sys.stdin.read().upper())",
        config=SandboxConfig(timeout_sec=10),
        stdin="hello",
    )
    assert result.ok is True
    assert "HELLO" in result.stdout


@pytest.mark.skipif(
    sys.platform != "linux",
    reason="RLIMIT_AS 在 macOS 是 no-op（Mach VM 设计）；mock 上的内存"
    "上限是 best-effort，真实隔离用 docker/Firecracker（PR #46）",
)
async def test_mock_python_memory_limit():
    """超内存上限：alloc 200MB 但 limit 128MB → 应失败（仅 Linux）"""
    rt = MockSandboxRuntime()
    result = await rt.execute(
        code="x = bytearray(200 * 1024 * 1024); print(len(x))",
        config=SandboxConfig(timeout_sec=10, memory_mb=128),
    )
    assert result.ok is False


async def test_mock_healthcheck_dev():
    rt = MockSandboxRuntime()
    assert await rt.healthcheck() is True


# ── 节点语言（如可用） ─────────────────────────────────


async def test_mock_node_hello(monkeypatch: pytest.MonkeyPatch):
    """若 node 不在 PATH 应抛 SandboxRuntimeError；在则正常跑"""
    import shutil as _shutil

    if not _shutil.which("node"):
        pytest.skip("node 不在 PATH")
    rt = MockSandboxRuntime()
    result = await rt.execute(
        code="console.log('hi from node')",
        config=SandboxConfig(language="node", timeout_sec=10),
    )
    assert result.ok is True
    assert "hi from node" in result.stdout
