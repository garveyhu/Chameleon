"""api_key 模块 DTO（Pydantic）

设计：
- ApiKeyItem: 列表/详情用，绝不含明文 key、绝不含 hash
- ApiKeyCreated: 创建响应，含 plain_key（仅一次回显）
- CreateApiKeyRequest: 创建入参
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateApiKeyRequest(BaseModel):
    app_id: str = Field(..., min_length=1, max_length=64, description="应用 slug")
    name: str = Field(..., min_length=1, max_length=128, description="可读名称")
    scopes: list[str] = Field(default_factory=list, description='["admin"] 或 []')
    description: str | None = None


class ApiKeyItem(BaseModel):
    id: int
    app_id: str
    name: str
    key_prefix: str
    scopes: list[str]
    description: str | None
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ApiKeyCreated(ApiKeyItem):
    """创建成功响应；plain_key 仅在创建时回显一次"""

    plain_key: str = Field(..., description="明文 key，仅此响应可见，请立即保存")
