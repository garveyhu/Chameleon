"""API collection chunker —— 解析 OpenAPI YAML/JSON

每个 endpoint 一 chunk：
- content：endpoint summary + description + 参数列表 + 响应类型摘要
- api_endpoint："GET /v1/users"
- meta.method / meta.path / meta.tags / meta.operation_id

config:
    {
      "include_tags": ["users", "auth"],   # 可选过滤；空 = 全部
      "include_deprecated": false
    }
"""

from __future__ import annotations

from typing import Any

import yaml
from loguru import logger

from chameleon.api.knowledge.chunkers.base import ChunkPayload

_HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


def chunk_api(
    text: str, config: dict[str, Any] | None = None
) -> list[ChunkPayload]:
    if not text or not text.strip():
        return []

    cfg = config or {}
    include_tags = set(cfg.get("include_tags") or [])
    include_deprecated = bool(cfg.get("include_deprecated", False))

    # 解析 YAML or JSON（yaml.safe_load 都能吃）
    try:
        spec = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"openapi 文档解析失败: {e}") from e

    if not isinstance(spec, dict) or "paths" not in spec:
        # 不是 OpenAPI 格式 → 回退 generic
        from chameleon.api.knowledge.chunkers.generic import chunk_generic

        logger.warning("API chunker 未检测到 openapi paths，回退 generic")
        return chunk_generic(text, {"mode": "paragraph"})

    paths = spec.get("paths") or {}
    out: list[ChunkPayload] = []
    seq = 0
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            if method.lower() not in _HTTP_METHODS:
                continue
            if not isinstance(op, dict):
                continue
            if op.get("deprecated") and not include_deprecated:
                continue
            op_tags = set(op.get("tags") or [])
            if include_tags and not (include_tags & op_tags):
                continue

            endpoint = f"{method.upper()} {path}"
            summary = (op.get("summary") or "").strip()
            description = (op.get("description") or "").strip()
            params = op.get("parameters") or []
            request_body = op.get("requestBody") or {}
            responses = op.get("responses") or {}

            content_parts = [endpoint]
            if summary:
                content_parts.append(f"摘要: {summary}")
            if description:
                content_parts.append(f"描述: {description}")
            if op_tags:
                content_parts.append(f"标签: {', '.join(sorted(op_tags))}")
            if params:
                lines = []
                for p in params:
                    if not isinstance(p, dict):
                        continue
                    lines.append(
                        f"  - {p.get('name','')} ({p.get('in','')})"
                        + (
                            f": {p.get('description','').strip()}"
                            if p.get("description")
                            else ""
                        )
                    )
                if lines:
                    content_parts.append("参数:\n" + "\n".join(lines))
            if request_body:
                content_parts.append(
                    f"请求体: {request_body.get('description','') or '见 schema'}"
                )
            if responses:
                resp_codes = ", ".join(sorted(responses.keys()))
                content_parts.append(f"响应码: {resp_codes}")

            content = "\n".join(content_parts).strip()
            out.append(
                ChunkPayload(
                    content=content,
                    index_name="chunk",
                    api_endpoint=endpoint[:256],
                    meta={
                        "method": method.upper(),
                        "path": path,
                        "tags": sorted(op_tags),
                        "operation_id": op.get("operationId"),
                        "seq": seq,
                    },
                )
            )
            seq += 1
    return out
