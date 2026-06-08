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


class DevStructuredRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(default_factory=list)
    #: 客户端传来的 JSON schema（作者 pydantic 类的 model_json_schema()）
    schema_: dict[str, Any] = Field(alias="schema")
    model: str | None = None


class DevMemoryRequest(BaseModel):
    action: str  # get / set / all
    key: str = ""
    value: Any = None


class DevCallAgentRequest(BaseModel):
    target: str
    input: str = ""
    # durable HITL：首次调用若 agent 暂停（ctx.ask_human）→ 响应带 run_id + pending；
    # 带 run_id + resume_call_index + resume_answer 重调即回填答案、重放续跑。
    run_id: str | None = None
    resume_call_index: int | None = None
    resume_answer: Any = None


class DevKbSearchRequest(BaseModel):
    query: str
    kbs: list[str] = Field(default_factory=list)
    top_k: int | None = None
    min_score: float = 0.0
    mode: str | None = None
    rerank: bool | None = None
    expand: int = 0
    hyde: bool = False


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
