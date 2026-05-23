"""Sandbox runtime —— P20.1 PR #45

替换 P18 ToolNode 里 `code` 类型的主进程 exec() 占位（**绝对禁止生产**）。
提供：抽象 SandboxRuntime + SandboxConfig/Result + registry。

PR #45 范围：协议层 + Mock 实现（dev/test 用 subprocess + resource limits）。
PR #46 加 docker / Firecracker 真实现；PR #47 接通 ToolNode。

红线（plan §2 P20 新增）：
- ⛔ Sandbox 永不在主进程跑用户代码 —— 必须子进程隔离 + 超时 + 资源上限
- ⛔ stdout/stderr 各 < 1MB；超出截断
- ⛔ 生产环境 (CHAMELEON_ENV=production) 拒绝加载 MockSandboxRuntime
"""

from chameleon.core.sandbox.runtime import (
    Language,
    Network,
    RuntimeName,
    SandboxConfig,
    SandboxResult,
    SandboxRuntime,
    SandboxRuntimeError,
    SandboxTimeoutError,
    SandboxOutputTooLargeError,
    get_runtime,
    list_runtime_names,
    register_runtime,
)

__all__ = [
    "Language",
    "Network",
    "RuntimeName",
    "SandboxConfig",
    "SandboxResult",
    "SandboxRuntime",
    "SandboxRuntimeError",
    "SandboxTimeoutError",
    "SandboxOutputTooLargeError",
    "get_runtime",
    "list_runtime_names",
    "register_runtime",
]
