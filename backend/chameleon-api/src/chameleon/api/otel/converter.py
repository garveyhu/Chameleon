"""OTLP → call_log 转换器 —— P22.2 PR #73

每个 OTEL span → 一行 call_log。映射规则：
- traceId + spanId → request_id（hex 拼）
- parentSpanId → parent_id
- name → 通过 attributes.gen_ai.* / openinference.* / scope.name 推断 observation_type
- start/end → duration_ms（按 nano）
- gen_ai.usage.* → prompt/completion/total tokens + cost_usd 自动算
- status.code == 2 (Error) → success=False
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.otel.schemas import KeyValue, Resource, Span
from chameleon.system.api_key.service import record_call

#: gen_ai/openinference span.name 关键词 → observation_type 映射
_TYPE_HINTS: list[tuple[str, str]] = [
    ("embedding", "embedding"),
    ("retriever", "retriever"),
    ("retrieval", "retriever"),
    ("tool", "tool"),
    ("agent", "agent"),
    ("chat.completion", "generation"),
    ("completion", "generation"),
    ("generation", "generation"),
    ("guardrail", "guardrail"),
]


def _attrs_to_dict(attrs: list[KeyValue]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kv in attrs:
        out[kv.key] = kv.value.value()
    return out


def _infer_observation_type(
    span_name: str, attrs: dict[str, Any], scope_name: str | None
) -> str:
    """从 span name / attributes / scope 推断 observation_type"""
    # 1) 显式 chameleon.observation_type 字段优先
    explicit = attrs.get("chameleon.observation_type")
    if isinstance(explicit, str):
        return explicit
    # 2) openinference span.kind
    oi_kind = attrs.get("openinference.span.kind")
    if isinstance(oi_kind, str):
        kind_lower = oi_kind.lower()
        if kind_lower in {"llm", "chain"}:
            return "generation"
        if kind_lower == "retriever":
            return "retriever"
        if kind_lower == "embedding":
            return "embedding"
        if kind_lower == "tool":
            return "tool"
        if kind_lower == "agent":
            return "agent"
    # 3) gen_ai system 存在 → generation
    if "gen_ai.system" in attrs:
        return "generation"
    # 4) name 子串匹配
    name_lower = (span_name or "").lower()
    for hint, t in _TYPE_HINTS:
        if hint in name_lower:
            return t
    # 5) scope name 兜底
    if scope_name and "openai" in scope_name.lower():
        return "generation"
    return "span"


def _resource_app_id(resource: Resource | None, header_app_id: str) -> str:
    """app_id 优先级：resource.attributes.chameleon.app_id > header

    注意：不接受 service.name —— SDK 写的 service.name 是 "chameleon-sdk"
    标识，不是业务 app_id；混用会触发 FK 违约。
    """
    if not resource:
        return header_app_id
    for kv in resource.attributes:
        if kv.key == "chameleon.app_id":
            v = kv.value.value()
            if isinstance(v, str) and v:
                return v
    return header_app_id


def _nano_to_ms(start_nano: str | int, end_nano: str | int) -> int:
    try:
        s = int(start_nano)
        e = int(end_nano)
        return max(0, (e - s) // 1_000_000)
    except (ValueError, TypeError):
        return 0


def _extract_tokens(
    attrs: dict[str, Any],
) -> tuple[int | None, int | None, int | None]:
    """从 gen_ai.usage.* 抽 tokens"""
    p = attrs.get("gen_ai.usage.prompt_tokens") or attrs.get(
        "gen_ai.usage.input_tokens"
    )
    c = attrs.get("gen_ai.usage.completion_tokens") or attrs.get(
        "gen_ai.usage.output_tokens"
    )
    t = attrs.get("gen_ai.usage.total_tokens")
    p_i = int(p) if p is not None else None
    c_i = int(c) if c is not None else None
    t_i = int(t) if t is not None else (
        (p_i or 0) + (c_i or 0) if (p_i or c_i) else None
    )
    return p_i, c_i, t_i


def _request_id_from(trace_id: str, span_id: str) -> str:
    """request_id 用 traceId-spanId 拼（≤ 64 chars）"""
    return f"{trace_id}-{span_id}"[:64]


async def convert_and_persist_span(
    session: AsyncSession,
    span: Span,
    *,
    resource: Resource | None,
    scope_name: str | None,
    app_id: str,
) -> None:
    """单 span → record_call 写一行 call_log"""
    attrs = _attrs_to_dict(span.attributes)
    obs_type = _infer_observation_type(span.name or "", attrs, scope_name)
    duration_ms = _nano_to_ms(span.startTimeUnixNano, span.endTimeUnixNano)
    p, c, total = _extract_tokens(attrs)
    success = span.status.code != 2  # 2 = Error
    code = 200 if success else 500
    err_msg = span.status.message if not success else None

    request_id = _request_id_from(span.traceId, span.spanId)
    parent_id = (
        _request_id_from(span.traceId, span.parentSpanId)
        if span.parentSpanId
        else None
    )

    model_code = attrs.get("gen_ai.request.model") or attrs.get(
        "gen_ai.response.model"
    )
    agent_key = (
        attrs.get("gen_ai.system")
        or attrs.get("chameleon.agent_key")
        or "otel-import"
    )

    request_payload = {
        "span_name": span.name,
        "scope": scope_name,
        "attributes": attrs,
    }
    response_payload = None

    resolved_app_id = _resource_app_id(resource, app_id)

    try:
        await record_call(
            session,
            request_id=request_id,
            app_id=resolved_app_id,
            agent_key=str(agent_key)[:64],
            session_id=attrs.get("chameleon.session_id"),
            stream=False,
            success=success,
            code=code,
            error_message=err_msg,
            duration_ms=duration_ms,
            prompt_tokens=p,
            completion_tokens=c,
            total_tokens=total,
            request_payload=request_payload,
            response_payload=response_payload,
            parent_id=parent_id,
            observation_type=obs_type,
            model_code=str(model_code) if model_code else None,
        )
    except Exception:
        logger.exception(
            "otel span persist failed | trace={} | span={}",
            span.traceId,
            span.spanId,
        )
        raise


def count_spans(req_resource_spans: list) -> int:
    """统计 ExportTraceServiceRequest 里总 span 数（供 logging）"""
    return sum(
        len(s.spans) for rs in req_resource_spans for s in rs.scopeSpans
    )


# 防 unused-import warning
_ = datetime, timezone
