"""SSE 事件类型 + payload 模型 + 构造 helper

为所有流式接口提供统一 chunk shape。本模块不动 wire format（仍是
扁平 dict 由 sse_response 包装），但用 Pydantic + helper 强制 service
产正确字段名 + 类型，避免拼写漂移。

### 用法

```python
from chameleon.core.api.sse_events import (
    UsagePayload,
    event_meta,
    event_delta,
    event_citation,
    event_end,
    event_error,
)

async def my_stream():
    yield event_meta(agent="echo", session_id="abc")
    async for token in llm.astream(...):
        yield event_delta(token)
    yield event_end(usage=UsagePayload(input_tokens=10, output_tokens=20), latency_ms=120)
```

### 事件类型总表（与前端 TS 镜像对齐）

| 事件 | 字段 | 触发时机 |
|------|------|----------|
| `meta`       | dict      | 流头部 1 次，告知上下文（model/agent/...） |
| `delta`      | str       | 每个文本片段 |
| `thought`    | ThoughtPayload | Agent 中间步骤（P18 启用） |
| `citation`   | CitationPayload | RAG 命中片段 |
| `node_start` | NodePayload | Workflow 节点开始（P18 启用） |
| `node_end`   | NodePayload | Workflow 节点结束（P18 启用） |
| `usage`      | UsagePayload | 单独的 usage 上报（一般合并进 end） |
| `end`        | dict + extras | 流末 1 次，含可选 usage + 业务扩展字段 |
| `error`      | ErrorPayload | 流中错误（之后不再有 end） |

### 一致性约束

- `delta` 永远是字符串
- `error` 出现后流即结束，service 不应再 yield 任何事件
- `end` 是流正常结束标记；错误流不应 yield end
- 业务扩展字段（如 model-test 的 `latency_ms` / embed 的 `answer`）允许
  通过 event_end 的 **extra 透传
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SSEEventKind(StrEnum):
    """所有 SSE 事件 kind —— 与 wire 上 dict 的顶层 key 对应"""

    META = "meta"
    DELTA = "delta"
    THOUGHT = "thought"
    CITATION = "citation"
    NODE_START = "node_start"
    NODE_END = "node_end"
    USAGE = "usage"
    END = "end"
    ERROR = "error"


# ── 共享 payload 模型 ────────────────────────────────────────


class UsagePayload(BaseModel):
    """LLM token 用量"""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "UsagePayload | None":
        if not raw:
            return None
        return cls(
            input_tokens=int(raw.get("input_tokens") or 0),
            output_tokens=int(raw.get("output_tokens") or 0),
            total_tokens=int(raw.get("total_tokens") or 0),
        )


class CitationPayload(BaseModel):
    """RAG 引用 —— extra=allow 让业务自由加字段（page、char_range 等）"""

    model_config = ConfigDict(extra="allow")

    source: str | None = None
    title: str | None = None
    snippet: str | None = None


class ErrorPayload(BaseModel):
    """流中错误"""

    type: str = Field(..., description="错误类型名（异常 class name 或自定义）")
    message: str = Field(..., description="错误信息（截断到 300 字符）")


class ThoughtPayload(BaseModel):
    """Agent 中间步骤 —— P18 GraphEngine 启用"""

    step: int = 0
    tool: str | None = None
    input: Any = None
    output: Any = None


class NodePayload(BaseModel):
    """Workflow 节点状态 —— P18 启用"""

    node_id: str
    node_type: str | None = None
    name: str | None = None
    status: str | None = None  # ok / error / running
    duration_ms: int | None = None


# ── 构造 helper —— service 调这些，不直接拼 dict ────────────


def event_meta(**fields: Any) -> dict[str, Any]:
    """流头部 meta 事件 —— 自由字段，业务自定义"""
    return {SSEEventKind.META.value: fields}


def event_delta(text: str) -> dict[str, Any]:
    """文本片段"""
    return {SSEEventKind.DELTA.value: text}


def event_citation(payload: CitationPayload | dict[str, Any]) -> dict[str, Any]:
    """RAG 命中 —— 支持 Pydantic model 或裸 dict 透传"""
    if isinstance(payload, CitationPayload):
        return {SSEEventKind.CITATION.value: payload.model_dump(exclude_none=True)}
    return {SSEEventKind.CITATION.value: payload}


def event_thought(payload: ThoughtPayload | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, ThoughtPayload):
        return {SSEEventKind.THOUGHT.value: payload.model_dump(exclude_none=True)}
    return {SSEEventKind.THOUGHT.value: payload}


def event_node_start(payload: NodePayload | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, NodePayload):
        return {SSEEventKind.NODE_START.value: payload.model_dump(exclude_none=True)}
    return {SSEEventKind.NODE_START.value: payload}


def event_node_end(payload: NodePayload | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, NodePayload):
        return {SSEEventKind.NODE_END.value: payload.model_dump(exclude_none=True)}
    return {SSEEventKind.NODE_END.value: payload}


def event_usage(usage: UsagePayload) -> dict[str, Any]:
    """单独 usage 事件（不带 end）"""
    return {SSEEventKind.USAGE.value: usage.model_dump()}


def event_end(
    usage: UsagePayload | dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """流末 end 事件 —— usage 可选，extra 透传业务字段

    例：
        event_end(usage=u, latency_ms=120, answer="...")
        → {"end": True, "usage": {...}, "latency_ms": 120, "answer": "..."}
    """
    out: dict[str, Any] = {SSEEventKind.END.value: True}
    if isinstance(usage, UsagePayload):
        out["usage"] = usage.model_dump()
    elif isinstance(usage, dict):
        out["usage"] = usage
    elif usage is None:
        out["usage"] = None
    out.update(extra)
    return out


def event_error(
    exc_or_type: Exception | str,
    message: str | None = None,
    *,
    max_message_len: int = 300,
) -> dict[str, Any]:
    """错误事件 —— 接受 Exception 或显式 (type, message)

    例：
        event_error(ValueError("bad")) → {"error":{"type":"ValueError","message":"bad"}}
        event_error("ConfigError", "missing base_url")
    """
    if isinstance(exc_or_type, Exception):
        payload = ErrorPayload(
            type=type(exc_or_type).__name__,
            message=str(exc_or_type)[:max_message_len],
        )
    else:
        if message is None:
            message = "unknown error"
        payload = ErrorPayload(
            type=exc_or_type,
            message=message[:max_message_len],
        )
    return {SSEEventKind.ERROR.value: payload.model_dump()}
