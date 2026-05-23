"""DockerSandboxRuntime —— 生产候选 #1（macOS / Linux dev 都跑得起）

每次调用起一次性 container：auto_remove=True + mem_limit + cpu_period/quota +
network_mode + tmpfs /tmp + pids_limit。docker-py 是同步 SDK，包到
asyncio.to_thread 里跑，主事件循环不阻塞。

红线（plan §2 P20）：
- ⛔ network=none / egress；'full' 禁用（在 SandboxConfig 已挡）
- ⛔ stdout/stderr 各 < max_*_bytes 截断
- ⛔ 容器 timeout 后强杀 + remove；容器泄漏会撑爆宿主
"""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Any

from loguru import logger

from chameleon.core.sandbox.runtime import (
    Language,
    SandboxConfig,
    SandboxResult,
    SandboxRuntime,
    SandboxRuntimeError,
)


_DEFAULT_IMAGES: dict[Language, str] = {
    "python": "python:3.12-alpine",
    "node": "node:20-alpine",
}


def _build_cmd(language: Language) -> list[str]:
    """通过环境变量喂代码（base64 避免 shell quoting）

    detach=True 时无法直接喂 stdin —— 用 env 传代码，shell 解码后管道执行。
    用户代码可读 stdin（CHM_SBX_STDIN 内容）+ 紧接 cat 透传剩余 stdin（空）。
    """
    if language == "python":
        return [
            "sh",
            "-c",
            'echo "$CHM_SBX_CODE_B64" | base64 -d > /tmp/main.py && '
            'echo "$CHM_SBX_STDIN" | python /tmp/main.py',
        ]
    if language == "node":
        return [
            "sh",
            "-c",
            'echo "$CHM_SBX_CODE_B64" | base64 -d > /tmp/main.js && '
            'echo "$CHM_SBX_STDIN" | node /tmp/main.js',
        ]
    raise SandboxRuntimeError(f"未支持的语言: {language}")


class DockerSandboxRuntime(SandboxRuntime):
    """docker-py SDK 实现"""

    name = "docker"

    def __init__(
        self,
        *,
        default_image: str | None = None,
        default_node_image: str | None = None,
    ) -> None:
        try:
            import docker
        except ImportError as e:
            raise SandboxRuntimeError(
                "docker SDK 未安装：pip install docker"
            ) from e

        try:
            self._client = docker.from_env(timeout=10)
        except Exception as e:
            raise SandboxRuntimeError(f"docker daemon 连接失败: {e}") from e

        self._default_image_py = default_image or _DEFAULT_IMAGES["python"]
        self._default_image_node = default_node_image or _DEFAULT_IMAGES["node"]

    async def healthcheck(self) -> bool:
        """ping daemon —— 失败返 False 让调用方降级 mock"""
        try:
            await asyncio.to_thread(self._client.ping)
            return True
        except Exception as e:
            logger.warning("docker daemon ping 失败：{}", e)
            return False

    async def execute(
        self,
        *,
        code: str,
        config: SandboxConfig,
        stdin: str = "",
    ) -> SandboxResult:
        image = config.image or self._pick_default_image(config.language)
        cmd = _build_cmd(config.language)

        # docker SDK 同步 API → 包到线程
        return await asyncio.to_thread(
            self._run_blocking, image, cmd, code, stdin, config
        )

    # ── 内部 ────────────────────────────────────────

    def _pick_default_image(self, language: Language) -> str:
        if language == "python":
            return self._default_image_py
        if language == "node":
            return self._default_image_node
        raise SandboxRuntimeError(f"未支持语言: {language}")

    def _run_blocking(
        self,
        image: str,
        cmd: list[str],
        code: str,
        stdin: str,
        config: SandboxConfig,
    ) -> SandboxResult:
        """同步路径：起容器 → 喂 stdin（代码） → wait → 取 logs → cleanup"""
        import docker  # noqa: F401（确保已可用）
        from docker.errors import (
            APIError,
            ContainerError,
            ImageNotFound,
            NotFound,
        )

        # CPU 配额：cpu_period 100ms = 100_000 微秒；quota = 0.5 核 → 50_000 微秒
        cpu_period = 100_000
        cpu_quota = max(1000, int(config.cpu_quota * cpu_period))

        network_mode = "none" if config.network == "none" else "bridge"

        # 代码用 base64 + env 喂；stdin 也走 env（命令行 echo 后管道）
        env = {
            **config.env,
            "CHAMELEON_SANDBOX": "docker",
            "CHM_SBX_CODE_B64": base64.b64encode(code.encode("utf-8")).decode("ascii"),
            "CHM_SBX_STDIN": stdin or "",
        }

        # 容器配置 dict（两处 create 复用）
        create_kwargs = dict(
            command=cmd,
            tty=False,
            detach=True,
            network_mode=network_mode,
            mem_limit=f"{config.memory_mb}m",
            memswap_limit=f"{config.memory_mb}m",  # 禁 swap
            cpu_period=cpu_period,
            cpu_quota=cpu_quota,
            pids_limit=64,
            read_only=True,  # rootfs 只读
            tmpfs={"/tmp": "size=64m,exec"},  # 临时区可写
            user="65534:65534",  # nobody:nogroup
            environment=env,
            cap_drop=["ALL"],  # 清空所有 capability
            security_opt=["no-new-privileges:true"],
        )

        start = time.monotonic()
        container = None
        timed_out = False
        try:
            try:
                container = self._client.containers.create(
                    image=image, **create_kwargs
                )
            except ImageNotFound:
                logger.info("docker image not found, pulling: {}", image)
                self._client.images.pull(image)
                container = self._client.containers.create(
                    image=image, **create_kwargs
                )

            container.start()

            try:
                wait_result = container.wait(timeout=config.timeout_sec)
                exit_code = int(wait_result.get("StatusCode", -1))
            except Exception as e:
                # docker-py wait 超时抛 ReadTimeoutError 等；视为 timeout
                logger.warning("docker wait timeout: {}", e)
                timed_out = True
                exit_code = -1
                try:
                    container.kill()
                except Exception:
                    pass

            # logs（拉全部 stdout/stderr，stream=False）
            stdout_bytes = container.logs(stdout=True, stderr=False)
            stderr_bytes = container.logs(stdout=False, stderr=True)

        except (APIError, ContainerError, NotFound) as e:
            raise SandboxRuntimeError(f"docker run 失败: {e}") from e
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception as e:
                    logger.warning(
                        "docker container remove failed: id={} err={}",
                        getattr(container, "id", "?"),
                        e,
                    )

        # 截断
        stdout_truncated = len(stdout_bytes) > config.max_stdout_bytes
        stderr_truncated = len(stderr_bytes) > config.max_stderr_bytes
        stdout = stdout_bytes[: config.max_stdout_bytes].decode(
            "utf-8", errors="replace"
        )
        stderr = stderr_bytes[: config.max_stderr_bytes].decode(
            "utf-8", errors="replace"
        )

        duration_ms = int((time.monotonic() - start) * 1000)

        meta: dict[str, Any] = {
            "runtime": "docker",
            "image": image,
            "network": config.network,
        }
        return SandboxResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            timed_out=timed_out,
            metadata=meta,
        )
