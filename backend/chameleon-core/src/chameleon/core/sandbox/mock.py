"""MockSandboxRuntime —— 仅 dev/test 用，**禁止生产**

实现：subprocess + resource.setrlimit + asyncio timeout。
- 隔离强度比 docker 弱（无 cgroup、无 namespace、共享 fs / 网络）
- 用 resource.setrlimit 给子进程设 RLIMIT_CPU / RLIMIT_AS 软上限
- 用 asyncio.wait_for 实现 timeout 强杀

红线（plan §2 P20 新增）：
- ⛔ 主进程不跑用户代码 —— 用 subprocess 起独立进程
- ⛔ 生产 (CHAMELEON_ENV=production) 拒绝加载 —— register 时检查
- ⛔ stdout/stderr 各 < max_*_bytes，超出截断
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from loguru import logger

from chameleon.core.sandbox.runtime import (
    Language,
    SandboxConfig,
    SandboxResult,
    SandboxRuntime,
    SandboxRuntimeError,
    is_production,
)


_PY_BIN_CACHE: dict[Language, str] = {}


def _resolve_interpreter(language: Language) -> str:
    """找解释器路径 —— python 用 sys.executable；node 走 which"""
    if language in _PY_BIN_CACHE:
        return _PY_BIN_CACHE[language]
    if language == "python":
        path = sys.executable
    elif language == "node":
        path = shutil.which("node") or ""
        if not path:
            raise SandboxRuntimeError(
                "MockSandboxRuntime: node 解释器未找到（PATH 里没有 node）"
            )
    else:
        raise SandboxRuntimeError(f"未支持的语言: {language}")
    _PY_BIN_CACHE[language] = path
    return path


def _setup_rlimits(memory_mb: int, cpu_seconds: int) -> None:
    """子进程 preexec_fn 钩子：设资源上限

    仅 Unix（macOS / Linux）；Windows 不进这里。

    每条 setrlimit 单独 try —— macOS 上 RLIMIT_AS 经常对 Python 解释器
    本身误杀；任何 preexec_fn 抛出都会让 subprocess 起不来
    (SubprocessError)，所以每条都吞掉，宁可放过也别炸掉。
    """
    try:
        import resource
    except ImportError:
        return

    # CPU 时间上限（秒；超时后内核 SIGXCPU）—— 最关键的闸门
    try:
        resource.setrlimit(
            resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1)
        )
    except (ValueError, OSError):
        pass
    # 虚拟内存上限 —— macOS Python 启动就 100+ MB；静默失败
    try:
        bytes_limit = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (bytes_limit, bytes_limit))
    except (ValueError, OSError):
        pass
    # 进程数上限 —— 防 fork 炸弹（macOS 不支持 → 吞）
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    except (ValueError, OSError, AttributeError):
        pass


class MockSandboxRuntime(SandboxRuntime):
    """subprocess 实现 —— dev/test 用，禁止上生产"""

    name = "mock"

    def __init__(self) -> None:
        if is_production():
            raise SandboxRuntimeError(
                "MockSandboxRuntime 拒绝在生产环境加载；"
                "请用 docker / firecracker runtime"
            )

    async def execute(
        self,
        *,
        code: str,
        config: SandboxConfig,
        stdin: str = "",
    ) -> SandboxResult:
        interpreter = _resolve_interpreter(config.language)
        cpu_sec = max(1, int(config.timeout_sec) + 1)

        # 把用户代码写到临时文件 —— 减少 shell 转义攻击面
        with tempfile.TemporaryDirectory(prefix="chameleon-sbx-") as tmpdir:
            script_path = Path(tmpdir) / (
                "main.py" if config.language == "python" else "main.js"
            )
            script_path.write_text(code, encoding="utf-8")

            # 网络策略：mock runtime 没有 namespace 隔离能力；仅在 env 设
            # 提示位（容器 runtime 在 PR #46 真正生效）。dev 提醒用 docker。
            env = {**os.environ, **config.env}
            env["CHAMELEON_SANDBOX"] = "mock"
            env["CHAMELEON_SANDBOX_NETWORK"] = config.network

            start = time.monotonic()
            try:
                # preexec_fn 不能跨平台；仅 Unix 设 rlimit
                preexec = (
                    (lambda: _setup_rlimits(config.memory_mb, cpu_sec))
                    if sys.platform != "win32"
                    else None
                )
                proc = await asyncio.create_subprocess_exec(
                    interpreter,
                    str(script_path),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=tmpdir,
                    env=env,
                    preexec_fn=preexec,
                )
            except FileNotFoundError as e:
                raise SandboxRuntimeError(
                    f"无法启动 {config.language} 解释器: {e}"
                )

            timed_out = False
            stdout_bytes = b""
            stderr_bytes = b""
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(input=stdin.encode("utf-8")),
                    timeout=config.timeout_sec,
                )
                exit_code = proc.returncode if proc.returncode is not None else -1
            except asyncio.TimeoutError:
                timed_out = True
                proc.kill()
                try:
                    await proc.wait()
                except Exception:
                    pass
                exit_code = -1
                logger.warning(
                    "sandbox timeout | pid={} | timeout={}s",
                    proc.pid,
                    config.timeout_sec,
                )

            duration_ms = int((time.monotonic() - start) * 1000)

            # 截断 stdout / stderr
            stdout_truncated = len(stdout_bytes) > config.max_stdout_bytes
            stderr_truncated = len(stderr_bytes) > config.max_stderr_bytes
            stdout = stdout_bytes[: config.max_stdout_bytes].decode(
                "utf-8", errors="replace"
            )
            stderr = stderr_bytes[: config.max_stderr_bytes].decode(
                "utf-8", errors="replace"
            )

        return SandboxResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            timed_out=timed_out,
            metadata={"runtime": "mock", "pid": proc.pid if proc else None},
        )

    async def healthcheck(self) -> bool:
        """dev 环境总是 healthy（解释器存在即可）"""
        try:
            _resolve_interpreter("python")
            return True
        except Exception:
            return False
