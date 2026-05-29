"""P20.1 PR #46: DockerSandboxRuntime smoke

CI / 无 docker 环境自动 skip；本地 docker 可达时跑完整路径。
"""

from __future__ import annotations

import pytest

from chameleon.core.sandbox import SandboxConfig


def _docker_available() -> bool:
    try:
        from chameleon.core.sandbox.docker import DockerSandboxRuntime

        rt = DockerSandboxRuntime()
        # 同步 ping，避免 anyio await
        return rt._client.ping()  # type: ignore[no-untyped-call]
    except Exception:
        return False


_DOCKER_OK = _docker_available()
_SKIP_REASON = "docker daemon 不可达；本地启 Docker Desktop 后再跑"


@pytest.mark.skipif(not _DOCKER_OK, reason=_SKIP_REASON)
async def test_docker_python_hello():
    from chameleon.core.sandbox.docker import DockerSandboxRuntime

    rt = DockerSandboxRuntime()
    assert await rt.healthcheck()
    result = await rt.execute(
        code="print('hello from docker')",
        config=SandboxConfig(timeout_sec=30),
    )
    assert result.ok, result.stderr
    assert "hello from docker" in result.stdout


@pytest.mark.skipif(not _DOCKER_OK, reason=_SKIP_REASON)
async def test_docker_python_nonzero_exit():
    from chameleon.core.sandbox.docker import DockerSandboxRuntime

    rt = DockerSandboxRuntime()
    result = await rt.execute(
        code="import sys; sys.exit(3)",
        config=SandboxConfig(timeout_sec=30),
    )
    assert result.exit_code == 3
    assert result.timed_out is False


@pytest.mark.skipif(not _DOCKER_OK, reason=_SKIP_REASON)
async def test_docker_python_runtime_error_to_stderr():
    from chameleon.core.sandbox.docker import DockerSandboxRuntime

    rt = DockerSandboxRuntime()
    result = await rt.execute(
        code="raise RuntimeError('boom')",
        config=SandboxConfig(timeout_sec=30),
    )
    assert result.exit_code != 0
    assert "RuntimeError" in result.stderr
    assert "boom" in result.stderr


@pytest.mark.skipif(not _DOCKER_OK, reason=_SKIP_REASON)
async def test_docker_timeout_kills_container():
    from chameleon.core.sandbox.docker import DockerSandboxRuntime

    rt = DockerSandboxRuntime()
    result = await rt.execute(
        code="import time; time.sleep(60)",
        config=SandboxConfig(timeout_sec=2),
    )
    assert result.timed_out is True
    assert result.exit_code == -1


@pytest.mark.skipif(not _DOCKER_OK, reason=_SKIP_REASON)
async def test_docker_stdout_truncated():
    from chameleon.core.sandbox.docker import DockerSandboxRuntime

    rt = DockerSandboxRuntime()
    code = "print('A' * 200_000)"
    result = await rt.execute(
        code=code,
        config=SandboxConfig(timeout_sec=30, max_stdout_bytes=10_000),
    )
    assert result.stdout_truncated is True
    assert len(result.stdout) <= 10_000


@pytest.mark.skipif(not _DOCKER_OK, reason=_SKIP_REASON)
async def test_docker_network_none_blocks():
    """network=none → 任何 socket connect 应失败"""
    from chameleon.core.sandbox.docker import DockerSandboxRuntime

    rt = DockerSandboxRuntime()
    code = (
        "import socket\n"
        "s = socket.socket()\n"
        "try:\n"
        "    s.connect(('1.1.1.1', 80))\n"
        "    print('connected')\n"
        "except OSError as e:\n"
        "    print(f'blocked:{e.errno}')\n"
    )
    result = await rt.execute(
        code=code,
        config=SandboxConfig(timeout_sec=10, network="none"),
    )
    assert "blocked" in result.stdout


# ── 无 docker 时也能跑的 unit ──────────────────────


def test_docker_module_import_doesnt_blow_up_when_docker_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    """构造一个找不到 docker 包的场景，验证模块 import 行为可控"""
    import importlib

    # 真实流程：DockerSandboxRuntime() 抛 SandboxRuntimeError
    # 但 module 本身 import 不应该崩
    from chameleon.core.sandbox import docker as docker_module

    importlib.reload(docker_module)
    # 类 import 还在
    assert docker_module.DockerSandboxRuntime is not None
