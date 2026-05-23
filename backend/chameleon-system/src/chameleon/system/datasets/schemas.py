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
