"""admin 模块 DTO"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CallLogItem(BaseModel):
    id: int
    request_id: str
    app_id: str
    agent_key: str
    session_id: str | None
    stream: bool
    success: bool
    code: int
    error_message: str | None
    duration_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProviderStatusItem(BaseModel):
    name: str
    ok: bool
    error: str | None = None
