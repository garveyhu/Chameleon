"""SandboxRuntime 抽象 + 数据模型 + 注册表

设计意图：让 ToolNode 不关心底层是 docker / Firecracker / subprocess，统一
SandboxRuntime.execute(code, config) → SandboxResult。
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

from loguru import logger

# ── 类型别名 ─────────────────────────────────────────────

Language = Literal["python", "node"]
"""sandbox 支持的语言"""

Network = Literal["none", "egress", "full"]
"""沙箱网络策略：none=禁；egress=仅出站；full=不限（暂禁用，留 P21）"""

RuntimeName = Literal["mock", "docker", "firecracker"]
"""注册过的 runtime 标识"""


# ── 输入 / 输出 dataclass ───────────────────────────────


@dataclass(frozen=True)
class SandboxConfig:
    """单次 sandbox 调用的运行配置

    所有上限值都有默认；调用方按需覆盖。
    """

    language: Language = "python"
    timeout_sec: float = 30.0
    memory_mb: int = 256
    cpu_quota: float = 0.5  # 0.5 = 半核
    network: Network = "none"
    max_stdout_bytes: int = 1024 * 1024  # 1MB
    max_stderr_bytes: int = 1024 * 1024
    # docker / firecracker 用：基础镜像；mock runtime 忽略
    image: str | None = None
    # 注入用户代码的环境变量（不要传敏感信息！sandbox 出错时可能 leak 到 logs）
    env: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # 数值上下界 sanity check —— 防 admin 配错
        if self.timeout_sec <= 0 or self.timeout_sec > 600:
            raise ValueError(
                f"timeout_sec 应在 (0, 600] 秒；当前={self.timeout_sec}"
            )
        if self.memory_mb < 32 or self.memory_mb > 4096:
            raise ValueError(
                f"memory_mb 应在 [32, 4096] MB；当前={self.memory_mb}"
            )
        if self.cpu_quota <= 0 or self.cpu_quota > 4:
            raise ValueError(
                f"cpu_quota 应在 (0, 4] 核；当前={self.cpu_quota}"
            )
        if self.max_stdout_bytes <= 0 or self.max_stderr_bytes <= 0:
            raise ValueError("max_stdout/stderr_bytes 必须 > 0")
        if self.network == "full":
            # 暂禁用 full，留 P21 再放
            raise ValueError(
                "network='full' 暂禁用；仅支持 'none' 和 'egress'"
            )


@dataclass(frozen=True)
class SandboxResult:
    """执行结果 —— 与运行时无关的统一形态"""

    stdout: str
    stderr: str
    exit_code: int  # 0 = 成功；非 0 = 运行错（含超时被信号 kill）
    duration_ms: int
    # 是否输出超限被截断
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    # 是否因 timeout 被强杀
    timed_out: bool = False
    # 运行时给的额外信息（如 oom_killed、container_id）
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


# ── 异常分类 ────────────────────────────────────────────


class SandboxRuntimeError(Exception):
    """sandbox runtime 自身错误（容器起不来 / 资源分配失败等）

    与"用户代码运行时报错"区分 —— 后者 exit_code 非 0 但 result 仍返回。
    """


class SandboxTimeoutError(SandboxRuntimeError):
    """超过 config.timeout_sec 后强杀"""


class SandboxOutputTooLargeError(SandboxRuntimeError):
    """输出超 max_stdout/stderr_bytes 且 runtime 选择 raise（默认截断不抛）"""


# ── ABC ─────────────────────────────────────────────────


class SandboxRuntime(ABC):
    """sandbox 后端抽象 —— 每种实现一类（mock / docker / firecracker）"""

    name: str  # runtime 唯一名；子类必须设

    @abstractmethod
    async def execute(
        self,
        *,
        code: str,
        config: SandboxConfig,
        stdin: str = "",
    ) -> SandboxResult:
        """运行 code 并返结果。

        异常约定：
        - SandboxRuntimeError 及其子类 → runtime 故障（容器挂、配置错），调用方 503
        - 用户代码非 0 退出 / runtime error → 不抛，stderr + exit_code 表达

        Args:
            code: 用户代码字符串
            config: 资源限制 + 语言 + 网络等
            stdin: 标准输入（默认空字符串）
        """
        raise NotImplementedError

    async def healthcheck(self) -> bool:
        """启动期可达性检查 —— docker daemon ping / Firecracker socket 等

        默认实现：True；子类按需重写。
        """
        return True


# ── 注册表 ────────────────────────────────────────────


_REGISTRY: dict[str, SandboxRuntime] = {}


def register_runtime(runtime: SandboxRuntime) -> None:
    """注册 SandboxRuntime 实例（按 .name 索引）"""
    if not getattr(runtime, "name", None):
        raise ValueError(
            f"SandboxRuntime 子类未设 name: {type(runtime).__name__}"
        )
    if runtime.name in _REGISTRY:
        logger.warning("sandbox runtime override | name={}", runtime.name)
    _REGISTRY[runtime.name] = runtime


def get_runtime(name: str) -> SandboxRuntime:
    """按 name 取 runtime —— 找不到 raise SandboxRuntimeError"""
    rt = _REGISTRY.get(name)
    if rt is None:
        raise SandboxRuntimeError(
            f"未知 sandbox runtime: {name!r}；已注册: {list_runtime_names()}"
        )
    return rt


def list_runtime_names() -> list[str]:
    return sorted(_REGISTRY.keys())


def is_production() -> bool:
    """生产环境识别 —— mock runtime 加载时检查这个"""
    return os.environ.get("CHAMELEON_ENV", "").lower() == "production"
