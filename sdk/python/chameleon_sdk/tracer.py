"""Trace / Span 对象 —— P22.2 PR #74

设计：
- Trace 是顶层容器；提供 span(name, observation_type) 创建嵌套 span
- Span 支持 with-block + set_usage / set_model / set_attribute / set_status
- 退出 with-block 自动 finish span（记录 end_time）并加入 trace.buffer
- Client.flush() 把 buffer 里的所有 spans 打包成 OTLP payload 上报
"""

from __future__ import annotations

import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chameleon_sdk.client import Client


def _hex(nbytes: int) -> str:
    return secrets.token_hex(nbytes)


@dataclass
class Span:
    """单个 span 记录（构造完后 finish 时落 buffer）"""

    name: str
    trace_id: str
    span_id: str = field(default_factory=lambda: _hex(8))
    parent_span_id: str | None = None
    observation_type: str = "span"
    start_unix_ns: int = field(default_factory=lambda: time.time_ns())
    end_unix_ns: int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status_code: int = 1  # 1=Ok, 2=Error
    status_message: str | None = None

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_usage(
        self,
        *,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
    ) -> None:
        if prompt_tokens is not None:
            self.attributes["gen_ai.usage.prompt_tokens"] = int(prompt_tokens)
        if completion_tokens is not None:
            self.attributes["gen_ai.usage.completion_tokens"] = int(
                completion_tokens
            )
        if total_tokens is not None:
            self.attributes["gen_ai.usage.total_tokens"] = int(total_tokens)

    def set_model(self, model: str, *, system: str = "openai") -> None:
        self.attributes["gen_ai.request.model"] = model
        self.attributes["gen_ai.system"] = system

    def set_status(self, code: int, message: str | None = None) -> None:
        """code: 1=Ok, 2=Error"""
        self.status_code = code
        self.status_message = message

    def to_otlp(self) -> dict:
        attrs = [
            _kv(k, v) for k, v in self.attributes.items() if v is not None
        ]
        return {
            "traceId": self.trace_id,
            "spanId": self.span_id,
            **({"parentSpanId": self.parent_span_id}
               if self.parent_span_id else {}),
            "name": self.name,
            "kind": 1,
            "startTimeUnixNano": str(self.start_unix_ns),
            "endTimeUnixNano": str(self.end_unix_ns or time.time_ns()),
            "attributes": attrs,
            "status": {
                "code": self.status_code,
                **({"message": self.status_message}
                   if self.status_message else {}),
            },
        }


def _kv(key: str, value: Any) -> dict:
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    return {"key": key, "value": {"stringValue": str(value)}}


@dataclass
class Trace:
    """一个 trace = 一组共享 trace_id 的 spans"""

    name: str
    client: "Client"
    trace_id: str = field(default_factory=lambda: _hex(16))
    _root_span: Span | None = None
    _stack: list[Span] = field(default_factory=list)

    def __enter__(self) -> "Trace":
        # 顶层 root span 用 trace.name
        self._root_span = Span(
            name=self.name,
            trace_id=self.trace_id,
            observation_type="trace",
        )
        self._stack.append(self._root_span)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # 关闭 root（如果还在栈里）
        if self._root_span and self._root_span.end_unix_ns is None:
            if exc:
                self._root_span.set_status(2, str(exc)[:200])
            self._root_span.end_unix_ns = time.time_ns()
            self.client._buffer_span(self._root_span)
        self._stack.clear()

    @contextmanager
    def span(
        self, name: str, *, observation_type: str = "span", **attrs: Any
    ):
        """嵌套 span context manager"""
        parent = self._stack[-1] if self._stack else None
        sp = Span(
            name=name,
            trace_id=self.trace_id,
            parent_span_id=parent.span_id if parent else None,
            observation_type=observation_type,
        )
        for k, v in attrs.items():
            sp.set_attribute(k, v)
        # 写 observation_type 到 attributes，让后端 converter 识别
        sp.set_attribute("chameleon.observation_type", observation_type)
        self._stack.append(sp)
        try:
            yield sp
        except Exception as e:
            sp.set_status(2, str(e)[:200])
            raise
        finally:
            sp.end_unix_ns = time.time_ns()
            self._stack.pop()
            self.client._buffer_span(sp)
