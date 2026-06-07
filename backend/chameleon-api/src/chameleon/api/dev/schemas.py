"""agentkit dev 端点 请求 / 响应 schema。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DevLlmRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(default_factory=list)
    model: str | None = None
    platform_tool_keys: list[str] = Field(default_factory=list)
    local_tool_schemas: list[dict[str, Any]] = Field(default_factory=list)


class DevLlmResponse(BaseModel):
    content: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, int] | None = None


class DevKbSearchRequest(BaseModel):
    query: str
    kbs: list[str] = Field(default_factory=list)
    top_k: int | None = None
    min_score: float = 0.0


class DevDoc(BaseModel):
    text: str
    score: float = 0.0
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DevToolExecRequest(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class DevToolItem(BaseModel):
    tool_key: str
    description: str = ""
