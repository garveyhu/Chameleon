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
    # P21.1 红线：PII 策略
    # - mask：preview / expected_output 内的 email/phone/id_card 替换占位符（默认）
    # - drop：含任意 PII 的 call_log 整条跳过，不入库
    # - keep：保留原文（明确知道无 PII 时；不推荐）
    pii_strategy: str = Field(default="mask", pattern="^(mask|drop|keep)$")


class SampleResult(BaseModel):
    """采样结果摘要"""

    dataset_id: int
    added: int
    skipped: int  # 已存在（同 source_call_log_id）跳过的数量
    # P21.1：因 PII drop 策略跳过的数量（与 skipped 区分）
    dropped_pii: int = 0


class UpdateItemRequest(BaseModel):
    """人工标注：改 expected_output / meta"""

    expected_output: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


class BulkImportItem(BaseModel):
    """手工 import 时单条 item 的入参（前端解析 CSV/JSONL 后构造）"""

    input_payload: dict[str, Any]
    expected_output: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


class BulkImportRequest(BaseModel):
    """批量 import items"""

    items: list[BulkImportItem] = Field(min_length=1, max_length=1000)
    # 同 sample：mask（默认）/ drop / keep
    pii_strategy: str = Field(default="mask", pattern="^(mask|drop|keep)$")


class BulkImportResult(BaseModel):
    dataset_id: int
    added: int
    dropped_pii: int = 0


# ── DatasetRun（PR #25） ──────────────────────────────────


class DatasetRunRequest(BaseModel):
    """跑一次 dataset"""

    name: str = Field(min_length=1, max_length=128)
    model_override: str | None = Field(default=None, max_length=64)
    prompt_override: str | None = None
    judge: str = Field(default="exact_match", max_length=32)
    # P21.2：可选 EvalTemplate 联动；跑完后按 template metrics 评分
    eval_template_id: int | None = None
    # A3：被测对象设为 agent（含 graph 编排的）；设了则整条工作流当被测，忽略 model_override
    agent_key: str | None = Field(default=None, max_length=64)


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


# ── P21.2 评分分布 ────────────────────────────────────


class ScoreBucket(BaseModel):
    """[low, high) 区间桶"""

    low: float
    high: float
    count: int


class MetricDistribution(BaseModel):
    metric_name: str
    mean: float | None = None
    buckets: list[ScoreBucket]
    low_score_item_ids: list[int]  # 低于 threshold 或 <0.5 的 item id


class ScoreDistributionResult(BaseModel):
    run_id: int
    threshold: float = 0.5
    total_scored_items: int
    metrics: list[MetricDistribution]
