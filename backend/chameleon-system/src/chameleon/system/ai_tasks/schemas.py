"""ai_tasks 域 schema —— 提交入参 / 任务出参。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SubmitAiTaskRequest(BaseModel):
    """提交一个 AI 任务。task_type 必须已在 ai_tasks registry 注册 handler。"""

    task_type: str = Field(min_length=1, max_length=64)
    scope: str | None = Field(default=None, max_length=64)
    scope_ref: str | None = Field(default=None, max_length=128)
    input: dict[str, Any] = Field(default_factory=dict)
    # True=跳过缓存强制新建（默认命中同输入的 success 任务直接复用）
    force: bool = False


class AiTaskItem(BaseModel):
    """AI 任务出参（轮询 / 列表 / 反显用）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    task_type: str
    scope: str | None = None
    scope_ref: str | None = None
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    model_code: str | None = None
    total_tokens: int | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
