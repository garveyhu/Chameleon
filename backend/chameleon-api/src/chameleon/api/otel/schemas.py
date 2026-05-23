"""OTLP HTTP/JSON 最小 schema —— P22.2 PR #73

只支持 traces（metrics / logs 留 v1.1）。仅 OTLP/JSON，protobuf 推后。

参考：
  https://opentelemetry.io/docs/specs/otlp/#otlphttp
  proto/opentelemetry/proto/trace/v1/trace.proto
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnyValue(BaseModel):
    """OTLP AnyValue —— 只取 5 种常用类型；其它当 string 兜底"""

    model_config = ConfigDict(extra="ignore")

    stringValue: str | None = None
    boolValue: bool | None = None
    intValue: int | str | None = None  # OTLP 用 string 表 int64
    doubleValue: float | None = None
    arrayValue: dict | None = None

    def value(self) -> Any:
        if self.stringValue is not None:
            return self.stringValue
        if self.boolValue is not None:
            return self.boolValue
        if self.intValue is not None:
            try:
                return int(self.intValue)
            except (ValueError, TypeError):
                return None
        if self.doubleValue is not None:
            return self.doubleValue
        return None


class KeyValue(BaseModel):
    model_config = ConfigDict(extra="ignore")
    key: str
    value: AnyValue = Field(default_factory=AnyValue)


class Resource(BaseModel):
    model_config = ConfigDict(extra="ignore")
    attributes: list[KeyValue] = Field(default_factory=list)


class InstrumentationScope(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = None
    version: str | None = None


class Status(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: int = 0  # 0=Unset, 1=Ok, 2=Error
    message: str | None = None


class Span(BaseModel):
    model_config = ConfigDict(extra="ignore")

    traceId: str  # 32 hex chars
    spanId: str   # 16 hex chars
    parentSpanId: str | None = None
    name: str
    kind: int = 0  # 0=Unspecified, 1=Internal, 2=Server, 3=Client, 4=Producer, 5=Consumer
    startTimeUnixNano: str | int
    endTimeUnixNano: str | int
    attributes: list[KeyValue] = Field(default_factory=list)
    status: Status = Field(default_factory=Status)


class ScopeSpans(BaseModel):
    model_config = ConfigDict(extra="ignore")
    scope: InstrumentationScope | None = None
    spans: list[Span] = Field(default_factory=list)


class ResourceSpans(BaseModel):
    model_config = ConfigDict(extra="ignore")
    resource: Resource | None = None
    scopeSpans: list[ScopeSpans] = Field(default_factory=list)


class ExportTraceServiceRequest(BaseModel):
    """OTLP/HTTP traces 入参"""

    model_config = ConfigDict(extra="ignore")
    resourceSpans: list[ResourceSpans] = Field(default_factory=list)


class ExportTraceServiceResponse(BaseModel):
    """OTLP/HTTP traces 响应"""

    partialSuccess: dict | None = None
