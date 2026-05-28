"""CodeNode —— 沙箱执行用户代码（对齐 Dify Code 节点）

把节点 input 作为 JSON 喂到 stdin，跑 data.code（python/node），stdout 若是 JSON 则
解析进 result。走 chameleon.core.sandbox（docker 优先，dev 兜底 mock）。

Phase D：inspector 开关 `mount_attachments` 时，把 sys.attachments 里每个文件下载
+ base64 编码追加到 stdin 的 input 里（`_attachments: [{filename, content_b64, mime, size}]`），
用户代码自取（避免要改 sandbox runtime 的 file mount 协议）。
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
from loguru import logger

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.node_base import Node
from chameleon.core.graph.registry import register_node_type

#: 单次注入 stdin 的附件总字节上限（防 stdin 爆掉）
_MAX_INJECT_BYTES = 10 * 1024 * 1024


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
        # Phase D：附件注入（受 inspector 开关 mount_attachments 控制）
        if data.get("mount_attachments"):
            atts = (
                (ctx.extra or {}).get("__vars__", {}).get("sys", {}).get("attachments")
                or []
            )
            if atts:
                injected = _download_and_encode(atts)
                if injected:
                    if isinstance(input, dict):
                        input = {**input, "_attachments": injected}
                    else:
                        input = {"_input": input, "_attachments": injected}

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


def _download_and_encode(atts: list[dict]) -> list[dict]:
    """下载附件 + base64 编码，受 _MAX_INJECT_BYTES 兜底"""
    out: list[dict] = []
    total = 0
    for a in atts:
        url = a.get("object_url")
        if not url:
            continue
        try:
            r = httpx.get(url, timeout=15.0)
            r.raise_for_status()
            data = r.content
        except Exception as e:  # noqa: BLE001
            logger.warning("CodeNode 附件下载失败 {}: {}", url, e)
            continue
        total += len(data)
        if total > _MAX_INJECT_BYTES:
            logger.warning(
                "CodeNode 附件总尺寸超过 {} 字节，截断剩余", _MAX_INJECT_BYTES
            )
            break
        out.append(
            {
                "filename": a.get("filename") or "",
                "mime": a.get("mime") or "application/octet-stream",
                "size": len(data),
                "content_b64": base64.b64encode(data).decode("ascii"),
            }
        )
    return out


register_node_type(CodeNode)
