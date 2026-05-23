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
    is_production,
    list_runtime_names,
    register_runtime,
)


async def bootstrap_runtimes() -> list[str]:
    """启动期注册可用 runtime —— lifespan 调

    策略：
    1. 试 docker daemon 可达 → 注册 DockerSandboxRuntime（生产首选）
    2. 非生产环境 → 兜底注册 MockSandboxRuntime（dev/test）

    返回已注册的 runtime name 列表。
    """
    from loguru import logger

    registered: list[str] = []
    # docker
    try:
        from chameleon.core.sandbox.docker import DockerSandboxRuntime

        rt = DockerSandboxRuntime()
        if await rt.healthcheck():
            register_runtime(rt)
            registered.append("docker")
            logger.info("sandbox runtime registered: docker")
        else:
            logger.warning("docker daemon 不可达 —— 跳过 docker runtime")
    except SandboxRuntimeError as e:
        logger.warning("docker runtime 不可用: {}", e)
    except Exception as e:  # noqa: BLE001
        logger.warning("docker runtime 初始化异常: {}", e)

    # mock —— 非生产才挂
    if not is_production():
        try:
            from chameleon.core.sandbox.mock import MockSandboxRuntime

            register_runtime(MockSandboxRuntime())
            registered.append("mock")
            logger.info("sandbox runtime registered: mock (dev only)")
        except SandboxRuntimeError as e:
            logger.warning("mock runtime 不可用: {}", e)

    if not registered:
        logger.warning(
            "无可用 sandbox runtime —— ToolNode 的 code 类型将拒绝执行"
        )
    return registered


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
    "bootstrap_runtimes",
    "get_runtime",
    "is_production",
    "list_runtime_names",
    "register_runtime",
]
