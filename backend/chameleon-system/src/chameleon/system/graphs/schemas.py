"""graphs DTO"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GraphItem(BaseModel):
    """graph 列表项（不含 spec）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    graph_key: str
    name: str
    description: str | None = None
    schema_version: int = 1
    enabled: bool
    # P22.3：published 版本字段
    published_version: int = 0
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class GraphDetail(GraphItem):
    """graph 详情：含完整 spec dict（draft + published 快照）"""

    spec: dict[str, Any]
    # P22.3：published 时 freeze 的快照（NULL = 从未 publish）
    published_spec: dict[str, Any] | None = None


class CreateGraphRequest(BaseModel):
    graph_key: str = Field(
        min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    spec: dict[str, Any] = Field(
        description="GraphSpec.model_dump()；后端会再校验一次"
    )


class UpdateGraphRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    spec: dict[str, Any] | None = None
    enabled: bool | None = None


class TestRunRequest(BaseModel):
    """临时跑一次 —— 不落 graph_runs，仅返结果（debug 用）"""

    input: dict[str, Any] = Field(default_factory=dict)


class NodeRunItem(BaseModel):
    """test-run 返的单节点执行摘要"""

    node_id: str
    node_type: str
    status: str
    input: Any | None = None
    output: Any | None = None
    error: dict[str, Any] | None = None
    duration_ms: int


class TestRunResult(BaseModel):
    status: str  # success / failed
    output: Any | None = None
    error: dict[str, Any] | None = None
    duration_ms: int
    node_runs: list[NodeRunItem]


class GraphRunRequest(BaseModel):
    """正式 run（持久化 + 写 call_logs）"""

    input: dict[str, Any] = Field(default_factory=dict)


class GraphRunItem(BaseModel):
    """graph_runs 列表项"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    graph_id: int
    request_id: str
    status: str
    duration_ms: int | None = None
    node_count: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class GraphRunDetail(GraphRunItem):
    """graph_runs 详情：含 input / output / error"""

    input: Any | None = None
    output: Any | None = None
    error: dict[str, Any] | None = None
