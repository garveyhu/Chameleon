"""Sandbox 实现层：docker / mock runtime + 启动期注册。

协议 + 注册表（SandboxRuntime / SandboxConfig / register_runtime / get_runtime …）
在 chameleon.core.sandbox（runtime）。这里只放具体 runtime 实现与 bootstrap。

红线（plan §2 P20）：
- ⛔ Sandbox 永不在主进程跑用户代码 —— 必须子进程隔离 + 超时 + 资源上限
- ⛔ 生产环境 (CHAMELEON_ENV=production) 拒绝加载 MockSandboxRuntime
"""

from chameleon.core.sandbox import (
    SandboxRuntimeError,
    is_production,
    register_runtime,
)
from chameleon.integrations.sandbox.docker import DockerSandboxRuntime
from chameleon.integrations.sandbox.mock import MockSandboxRuntime


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
            register_runtime(MockSandboxRuntime())
            registered.append("mock")
            logger.info("sandbox runtime registered: mock (dev only)")
        except SandboxRuntimeError as e:
            logger.warning("mock runtime 不可用: {}", e)

    if not registered:
        logger.warning("无可用 sandbox runtime —— ToolNode 的 code 类型将拒绝执行")
    return registered


__all__ = [
    "DockerSandboxRuntime",
    "MockSandboxRuntime",
    "bootstrap_runtimes",
]
