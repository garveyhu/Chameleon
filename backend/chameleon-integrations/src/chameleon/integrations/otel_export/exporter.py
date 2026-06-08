"""OTel 出站 exporter —— 把 Chameleon 的 trace 导出到外部 OTLP 收集器。

让用户把 call_log trace 树接进自己已有的 observability（LangSmith / Langfuse / Phoenix /
Arize 等），解除「trace 数据锁死在 Chameleon」的顾虑——世界级编排框架的可采用性前提。

零重依赖：手搓 OTLP/HTTP JSON（protobuf-JSON 映射）经 httpx POST 到 endpoint，按 GenAI
semantic convention（gen_ai.*）映射属性（与入站 otel/converter.py 的映射互为镜像）。

配置：CHAMELEON_OTEL_EXPORT_ENDPOINT（如 http://host:4318/v1/traces）+ 可选
CHAMELEON_OTEL_EXPORT_HEADERS（"k=v,k2=v2"，鉴权）。
"""

from __future__ import annotations

import hashlib
from typing import Any

from loguru import logger


def export_endpoint() -> str | None:
    from chameleon.core.config.env_settings import env_settings

    return env_settings.CHAMELEON_OTEL_EXPORT_ENDPOINT


def should_export() -> bool:
    return bool(export_endpoint())


def _hex(value: str | None, width: int) -> str:
    """把任意 id 字符串稳定派生成 width 位 hex（trace=32 / span=16）。"""
    h = hashlib.sha256((value or "").encode()).hexdigest()
    return h[:width]


def _attr(key: str, value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    return {"key": key, "value": {"stringValue": str(value)}}


def _row_to_span(row: dict[str, Any], trace_id: str) -> dict[str, Any]:
    start_ns = int(row.get("start_unix_nano") or 0)
    end_ns = start_ns + int(row.get("duration_ms") or 0) * 1_000_000
    otype = row.get("observation_type") or "span"
    attrs = [
        _attr("chameleon.observation_type", otype),
        _attr("chameleon.channel", row.get("channel")),
        _attr("chameleon.agent_key", row.get("agent_key")),
        _attr("gen_ai.usage.input_tokens", row.get("prompt_tokens")),
        _attr("gen_ai.usage.output_tokens", row.get("completion_tokens")),
        _attr("gen_ai.usage.total_tokens", row.get("total_tokens")),
        _attr("gen_ai.usage.cost", row.get("cost_usd")),
    ]
    model = row.get("model_code")
    if model:
        attrs.append(_attr("gen_ai.request.model", model))
        if otype == "generation":
            attrs.append(_attr("gen_ai.system", model))
    span: dict[str, Any] = {
        "traceId": trace_id,
        "spanId": _hex(row.get("request_id"), 16),
        "name": row.get("name") or otype,
        "kind": 1,  # SPAN_KIND_INTERNAL
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": [a for a in attrs if a is not None],
    }
    if row.get("parent_id"):
        span["parentSpanId"] = _hex(row.get("parent_id"), 16)
    if row.get("success") is False:
        span["status"] = {"code": 2, "message": (row.get("error_message") or "")[:200]}  # ERROR
    return span


def build_otlp_payload(root_request_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """把一条 trace 的 call_log 行映射成 OTLP/HTTP traces JSON（纯函数，可单测）。"""
    trace_id = _hex(root_request_id, 32)
    spans = [_row_to_span(r, trace_id) for r in rows]
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [_attr("service.name", "chameleon")],
                },
                "scopeSpans": [{"scope": {"name": "chameleon"}, "spans": spans}],
            }
        ]
    }


def _parse_headers(raw: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in (raw or "").split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k.strip()] = v.strip()
    return out


async def export_trace(root_request_id: str) -> None:
    """查 root_request_id 的整棵 trace（根 + 子行）→ 构 OTLP → POST。fire-and-forget 安全。"""
    endpoint = export_endpoint()
    if not endpoint:
        return
    try:
        import httpx
        from sqlalchemy import or_, select

        from chameleon.core.config.env_settings import env_settings
        from chameleon.data.infra.db import AsyncSessionLocal
        from chameleon.data.models import CallLog

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CallLog).where(
                    or_(
                        CallLog.request_id == root_request_id,
                        CallLog.parent_id == root_request_id,
                        CallLog.parent_id.like(f"{root_request_id}.%"),
                    )
                )
            )
            call_logs = result.scalars().all()
        if not call_logs:
            return
        rows = [
            {
                "request_id": c.request_id,
                "parent_id": c.parent_id,
                "observation_type": getattr(c, "observation_type", None),
                "name": getattr(c, "name", None),
                "model_code": getattr(c, "model_code", None),
                "prompt_tokens": getattr(c, "prompt_tokens", None),
                "completion_tokens": getattr(c, "completion_tokens", None),
                "total_tokens": getattr(c, "total_tokens", None),
                "cost_usd": float(c.cost_usd) if getattr(c, "cost_usd", None) is not None else None,
                "duration_ms": getattr(c, "duration_ms", None),
                "channel": getattr(c, "channel", None),
                "agent_key": getattr(c, "agent_key", None),
                "success": getattr(c, "success", None),
                "error_message": getattr(c, "error_message", None),
                "start_unix_nano": int(c.created_at.timestamp() * 1e9)
                if getattr(c, "created_at", None)
                else 0,
            }
            for c in call_logs
        ]
        payload = build_otlp_payload(root_request_id, rows)
        headers = {"Content-Type": "application/json"}
        headers.update(_parse_headers(env_settings.CHAMELEON_OTEL_EXPORT_HEADERS))
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
        logger.debug(
            "otel export | trace={} spans={} status={}",
            root_request_id, len(rows), resp.status_code,
        )
    except Exception:  # noqa: BLE001
        logger.warning("otel export 失败 trace={}（不影响主流程）", root_request_id)
