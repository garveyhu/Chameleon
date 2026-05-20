"""task 模块 DTO"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TaskItem(BaseModel):
    id: int
    task_type: str
    ref_type: str | None
    ref_id: int | None
    status: str
    progress: int
    message: str | None
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    app_id: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
