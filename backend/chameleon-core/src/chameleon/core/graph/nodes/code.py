"""CodeNode —— 沙箱执行用户代码（对齐 Dify Code 节点）

把节点 input 作为 JSON 喂到 stdin，跑 data.code（python/node），stdout 若是 JSON 则
解析进 result。走 chameleon.core.sandbox（docker 优先，dev 兜底 mock）。
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.node_base import Node
from chameleon.core.graph.registry import register_node_type


class CodeNode(Node[Any, dict]):
    """沙箱代码节点（type='code'）"""

    type = "code"

    def validate_data(self, data: dict[str, Any]) -> None:
        if not isinstance(data.get("code"), str) or not data["code"].strip():
            raise ValueError("CodeNode.data.code 必填（string）")
        lang = data.get("language", "python")
        if lang not in ("python", "node"):
            raise ValueError("CodeNode.data.language ∈ python|node")

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        from chameleon.core.sandbox import (
            SandboxConfig,
            SandboxRuntimeError,
            get_runtime,
            list_runtime_names,
        )

        data = self.spec.data
        available = list_runtime_names()
        if "docker" in available:
            rt = get_runtime("docker")
        elif "mock" in available:
            rt = get_runtime("mock")
        else:
            raise RuntimeError("无可用 sandbox runtime（docker 不可达且非 dev）")

        cfg = SandboxConfig(
            language=data.get("language", "python"),
            timeout_sec=float(data.get("timeout_sec", 30)),
            network=data.get("network", "none"),
        )
        stdin = (
            json.dumps(input, ensure_ascii=False, default=str)
            if input is not None
            else ""
        )
        logger.debug("CodeNode {} | runtime={} | lang={}", self.id, rt.name, cfg.language)
        try:
            result = await rt.execute(code=data["code"], config=cfg, stdin=stdin)
        except SandboxRuntimeError as e:
            raise RuntimeError(f"sandbox 运行失败：{e}") from e

        out: dict[str, Any] = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
        }
        try:
            out["result"] = json.loads(result.stdout)
        except (ValueError, json.JSONDecodeError):
            pass
        return out


register_node_type(CodeNode)
