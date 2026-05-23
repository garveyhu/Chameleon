"""datasets DTO"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DatasetItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    item_count: int
    created_at: datetime
    updated_at: datetime


class DatasetDetail(DatasetItem):
    """详情同列表项（v0.4 暂无额外字段）"""

    pass


class CreateDatasetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)


class UpdateDatasetRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=2000)


class DatasetItemItem(BaseModel):
    """dataset_items 出参（已脱敏）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    source_call_log_id: str | None = None
    input_payload: dict[str, Any]
    expected_output: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class SampleFromLogsRequest(BaseModel):
    """按 filter 采样 call_log → dataset_items（默认脱敏）"""

    app_id: str | None = None
    agent_key: str | None = None
    success: bool | None = None
    since: datetime | None = None
    until: datetime | None = None
    # 仅采前 N 条；默认 50，最大 500
    limit: int = Field(default=50, ge=1, le=500)
    # 是否同时把 response_payload 也带入 expected_output（人工标注前的"金标准"）
    include_response_as_expected: bool = True


class SampleResult(BaseModel):
    """采样结果摘要"""

    dataset_id: int
    added: int
    skipped: int  # 已存在（同 source_call_log_id）跳过的数量


class UpdateItemRequest(BaseModel):
    """人工标注：改 expected_output / meta"""

    expected_output: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


# ── DatasetRun（PR #25） ──────────────────────────────────


class DatasetRunRequest(BaseModel):
    """跑一次 dataset"""

    name: str = Field(min_length=1, max_length=128)
    model_override: str | None = Field(default=None, max_length=64)
    prompt_override: str | None = None
    judge: str = Field(default="exact_match", max_length=32)


class DatasetRunItemRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_run_id: int
    dataset_item_id: int
    actual_output: dict[str, Any] | None = None
    score: float | None = None
    error: dict[str, Any] | None = None
    duration_ms: int | None = None


class DatasetRunRow(BaseModel):
    """列表项"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    name: str
    model_override: str | None = None
    judge: str
    status: str
    summary: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class DatasetRunDetail(DatasetRunRow):
    """详情（含 prompt_override）"""

    agent_key: str | None = None
    prompt_override: str | None = None


class CompareRunsRequest(BaseModel):
    """对比 N 个 run 的 item-by-item 表"""

    run_ids: list[int] = Field(min_length=1, max_length=5)


class CompareItemCell(BaseModel):
    """每个对比单元：item + 各 run 的 score / actual"""

    dataset_item_id: int
    input_preview: str | None = None  # 已脱敏的展示文案
    expected_output: dict[str, Any] | None = None
    cells: dict[int, DatasetRunItemRow] = Field(default_factory=dict)


class CompareRunsResult(BaseModel):
    runs: list[DatasetRunRow]
    rows: list[CompareItemCell]
