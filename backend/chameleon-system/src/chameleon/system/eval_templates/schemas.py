"""eval_templates DTO —— P21.2 PR #62"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MetricSpec(BaseModel):
    """单个 metric 配置"""

    name: str = Field(min_length=1, max_length=64)
    # 算法 key（RAGAS / 自定义）；P21.2 PR #63 落 4 个 builtin
    algorithm: str = Field(min_length=1, max_length=64)
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    # 算法相关参数（如 LLM judge model、retry 等）
    config: dict | None = None


class EvalTemplateItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    metrics: list[dict]
    judge_provider: str | None = None
    version: int
    workspace_id: int | None = None
    created_at: datetime
    updated_at: datetime


class CreateEvalTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    metrics: list[MetricSpec] = Field(min_length=1, max_length=20)
    judge_provider: str | None = Field(default=None, max_length=64)

    @field_validator("metrics")
    @classmethod
    def _weights_sum_in_range(cls, v: list[MetricSpec]) -> list[MetricSpec]:
        total = sum(m.weight for m in v)
        if total <= 0:
            raise ValueError("metrics weights 总和必须 > 0")
        # 不强求 sum=1（允许 admin 用相对权重；评分时归一化）
        return v


class UpdateEvalTemplateRequest(BaseModel):
    """update → version += 1；老 EvalJob 引用 freeze 不动"""

    description: str | None = Field(default=None, max_length=2000)
    metrics: list[MetricSpec] | None = Field(default=None, min_length=1, max_length=20)
    judge_provider: str | None = Field(default=None, max_length=64)
