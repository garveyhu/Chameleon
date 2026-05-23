"""eval_jobs DTO"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EvalJobItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_key: str
    name: str
    description: str | None = None
    dataset_id: int
    target_kind: str
    target_key: str | None = None
    model_override: str | None = None
    prompt_override: str | None = None
    judge: str
    cron_expr: str
    alert_config: dict[str, Any] | None = None
    enabled: bool
    last_run_at: datetime | None = None
    last_score: Decimal | None = None
    created_at: datetime
    updated_at: datetime


class CreateEvalJobRequest(BaseModel):
    job_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-:.]+$")
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    dataset_id: int
    target_kind: Literal["agent", "graph"] = "agent"
    target_key: str | None = None
    model_override: str | None = None
    prompt_override: str | None = None
    judge: str = "exact_match"
    cron_expr: str = Field(min_length=1, max_length=64)
    alert_config: dict[str, Any] | None = None
    enabled: bool = True


class UpdateEvalJobRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    target_kind: Literal["agent", "graph"] | None = None
    target_key: str | None = None
    model_override: str | None = None
    prompt_override: str | None = None
    judge: str | None = None
    cron_expr: str | None = Field(default=None, max_length=64)
    alert_config: dict[str, Any] | None = None
    enabled: bool | None = None


class EvalJobRunItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    dataset_run_id: int | None = None
    triggered_by: str
    status: str
    mean_score: Decimal | None = None
    delta_score: Decimal | None = None
    alert_sent: bool
    alert_target: str | None = None
    error: dict[str, Any] | None = None
    created_at: datetime
    finished_at: datetime | None = None


class TriggerEvalJobResult(BaseModel):
    job_run_id: int
    dataset_run_id: int | None = None
    status: str
    mean_score: Decimal | None = None
