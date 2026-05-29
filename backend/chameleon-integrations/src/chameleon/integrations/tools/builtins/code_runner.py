"""CodeRunnerTool —— P20.1 PR #47

调 SandboxRuntime 跑用户代码（python / node）。Tool 自己不做隔离，全部委托
给 sandbox runtime（docker / mock）。

参数（args）：
    {
      "code": "print(...)",
      "language": "python" | "node",      # 默认 python
      "stdin": "..."                       # 可选标准输入
    }

config（admin tool_instances）：
    {
      "runtime": "docker" | "mock",       # 默认 'docker' 不可达就回退 'mock'
      "image": "python:3.12-alpine",      # docker 专用
      "timeout_sec": 30,
      "memory_mb": 256,
      "cpu_quota": 0.5,
      "network": "none" | "egress",
      "max_stdout_bytes": 1048576
    }

返回：
    ToolResult(
      data={"stdout": ..., "stderr": ..., "exit_code": 0, "duration_ms": 12,
            "timed_out": false, "stdout_truncated": false},
      meta={"runtime": "docker", "image": "...", "network": "none"}
    )
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from chameleon.core.sandbox import (
    SandboxConfig,
    SandboxRuntimeError,
    get_runtime,
    list_runtime_names,
)
from chameleon.core.tools.base import Tool, ToolContext, ToolResult
from chameleon.integrations.tools.registry import register_tool


class CodeRunnerTool(Tool):
    tool_key = "code-runner"
    description = (
        "在隔离 sandbox 跑 python / node 代码（docker / mock runtime）"
    )
    # 默认不启用 —— 像 SQLTool 一样，admin 显式开 + 配 runtime/image
    default_enabled = False

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "用户代码（注意 stdout/stderr 1MB 截断）",
                },
                "language": {
                    "type": "string",
                    "enum": ["python", "node"],
                },
                "stdin": {"type": "string"},
            },
            "required": ["code"],
        }

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        code = args.get("code", "")
        language = args.get("language", "python")
        stdin = args.get("stdin", "")

        if not code or not isinstance(code, str):
            return ToolResult(ok=False, error="code 必填且必须是字符串")

        cfg_dict: dict[str, Any] = dict(self.config or {})
        runtime_name = cfg_dict.pop("runtime", None)

        # 选 runtime：admin 显式指定 → 找；未指定 → 优先 docker，否则 mock
        rt = None
        available = list_runtime_names()
        try:
            if runtime_name:
                rt = get_runtime(runtime_name)
            elif "docker" in available:
                rt = get_runtime("docker")
            elif "mock" in available:
                rt = get_runtime("mock")
            else:
                return ToolResult(ok=False, error=
                    "无可用 sandbox runtime（docker 不可达且非 dev 环境）"
                )
        except SandboxRuntimeError as e:
            return ToolResult(ok=False, error=f"sandbox runtime 不可用：{e}")

        # 把 admin config 映射到 SandboxConfig，未给的项走默认值
        try:
            sb_config = SandboxConfig(
                language=language,
                timeout_sec=float(cfg_dict.get("timeout_sec", 30)),
                memory_mb=int(cfg_dict.get("memory_mb", 256)),
                cpu_quota=float(cfg_dict.get("cpu_quota", 0.5)),
                network=cfg_dict.get("network", "none"),
                max_stdout_bytes=int(
                    cfg_dict.get("max_stdout_bytes", 1024 * 1024)
                ),
                max_stderr_bytes=int(
                    cfg_dict.get("max_stderr_bytes", 1024 * 1024)
                ),
                image=cfg_dict.get("image"),
            )
        except ValueError as e:
            return ToolResult(ok=False, error=f"sandbox config 非法：{e}")

        logger.info(
            "code-runner | runtime={} | language={} | timeout={}s",
            rt.name,
            language,
            sb_config.timeout_sec,
        )
        try:
            result = await rt.execute(code=code, config=sb_config, stdin=stdin)
        except SandboxRuntimeError as e:
            return ToolResult(ok=False, error=f"sandbox 运行失败：{e}")

        data = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "stdout_truncated": result.stdout_truncated,
            "stderr_truncated": result.stderr_truncated,
            "timed_out": result.timed_out,
        }
        # Tool 层"成功"= sandbox 自己跑通；用户代码非 0 退出仍 ok=True，
        # 由调用方按 data.exit_code / data.timed_out 判定业务结果。
        meta = dict(result.metadata)
        if not result.ok:
            meta["user_code_failed"] = True
        return ToolResult(ok=True, data=data, meta=meta)


register_tool(CodeRunnerTool)
