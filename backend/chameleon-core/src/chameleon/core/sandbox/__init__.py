"""Sandbox runtime —— 协议层 + registry。

提供：抽象 SandboxRuntime + SandboxConfig/Result + 异常 + registry
（register_runtime / get_runtime / list_runtime_names / is_production）。

具体实现（docker / mock runtime）与启动期注册（bootstrap_runtimes）已移到
chameleon.integrations.sandbox。core 只留协议与注册表。

红线（plan §2 P20）：
- ⛔ Sandbox 永不在主进程跑用户代码 —— 必须子进程隔离 + 超时 + 资源上限
- ⛔ stdout/stderr 各 < 1MB；超出截断
- ⛔ 生产环境 (CHAMELEON_ENV=production) 拒绝加载 MockSandboxRuntime
"""

from chameleon.core.sandbox.runtime import (
    Language,
    Network,
    RuntimeName,
    SandboxConfig,
    SandboxOutputTooLargeError,
    SandboxResult,
    SandboxRuntime,
    SandboxRuntimeError,
    SandboxTimeoutError,
    get_runtime,
    is_production,
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
    "is_production",
    "list_runtime_names",
    "register_runtime",
]
