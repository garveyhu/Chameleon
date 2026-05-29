"""scores DTO"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ScoreDataType = Literal["numeric", "categorical", "boolean", "text"]
ScoreSource = Literal["annotation", "api", "eval", "feedback"]


class ScoreItem(BaseModel):
    """score 出参"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    call_log_id: str
    trace_id: str | None = None
    name: str
    value: float | None = None
    string_value: str | None = None
    data_type: ScoreDataType
    source: ScoreSource
    comment: str | None = None
    created_at: datetime


class CreateScoreRequest(BaseModel):
    """admin 主动写入 score（标注 / 人工评分）

    数值评分填 value；分类 / 文本评分填 string_value；
    至少有一个非空，data_type 必须匹配。
    """

    call_log_id: str = Field(min_length=1, max_length=64)
    trace_id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    value: float | None = None
    string_value: str | None = None
    data_type: ScoreDataType = "numeric"
    source: ScoreSource = "api"
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _validate_value_consistency(self) -> "CreateScoreRequest":
        if self.data_type in ("numeric", "boolean") and self.value is None:
            raise ValueError(f"data_type={self.data_type} 要求 value 非空")
        if self.data_type in ("categorical", "text") and not self.string_value:
            raise ValueError(
                f"data_type={self.data_type} 要求 string_value 非空"
            )
        return self


class FeedbackRequest(BaseModel):
    """widget / 业务侧反馈入参

    简化版：默认 source='feedback'，data_type 自动推断（value→numeric，
    string_value→categorical）。
    """

    trace_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    value: float | None = None
    string_value: str | None = None
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _validate_payload(self) -> "FeedbackRequest":
        if self.value is None and not self.string_value:
            raise ValueError("value 与 string_value 至少有一个")
        return self
