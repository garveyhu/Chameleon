"""SpanRecorder —— invoke 链路时间打点

用法：
    rec = SpanRecorder(t0=time.perf_counter())
    with rec.span("agent_resolve"):
        ...
    with rec.span("provider_invoke", meta={"provider": "dify"}):
        ...
    spans = rec.dump()  # → [{name, start_ms, end_ms, status, error?, meta?}, ...]

每 span 的 start_ms / end_ms 相对 t0 计算（毫秒）；status 默认 success，
异常时自动捕获 error_class + message 并标 failed。
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Span:
    name: str
    start_ms: float
    end_ms: float | None = None
    status: str = "running"
    error_class: str | None = None
    error_message: str | None = None
    meta: dict[str, Any] | None = None


@dataclass
class SpanRecorder:
    t0: float = field(default_factory=time.perf_counter)
    _spans: list[_Span] = field(default_factory=list)

    def now_ms(self) -> float:
        return (time.perf_counter() - self.t0) * 1000.0

    def add(
        self,
        name: str,
        *,
        start_ms: float,
        end_ms: float,
        status: str = "success",
        meta: dict[str, Any] | None = None,
        error_class: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self._spans.append(
            _Span(
                name=name,
                start_ms=round(start_ms, 1),
                end_ms=round(end_ms, 1),
                status=status,
                error_class=error_class,
                error_message=error_message,
                meta=meta,
            )
        )

    @contextmanager
    def span(self, name: str, *, meta: dict[str, Any] | None = None):
        start = self.now_ms()
        rec = _Span(name=name, start_ms=round(start, 1), meta=meta)
        self._spans.append(rec)
        try:
            yield rec
        except Exception as e:  # noqa: BLE001
            rec.end_ms = round(self.now_ms(), 1)
            rec.status = "failed"
            rec.error_class = type(e).__name__
            rec.error_message = str(e)[:300]
            raise
        else:
            rec.end_ms = round(self.now_ms(), 1)
            rec.status = "success"

    def dump(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for s in self._spans:
            entry: dict[str, Any] = {
                "name": s.name,
                "start_ms": s.start_ms,
                "end_ms": s.end_ms if s.end_ms is not None else s.start_ms,
                "status": s.status,
            }
            if s.error_class:
                entry["error_class"] = s.error_class
            if s.error_message:
                entry["error_message"] = s.error_message
            if s.meta:
                entry["meta"] = s.meta
            out.append(entry)
        return out
