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
    # 作用域域：app（通吃）/ agent（某智能体）/ kb（某知识库）
    scope_type: str = Field(default="app", pattern="^(app|agent|kb)$")
    scope_ref: str | None = Field(
        None, description="域内目标：agent→agent_key、kb→kb_key、app→空"
    )


class ApiKeyItem(BaseModel):
    id: int
    app_id: str
    name: str
    key_prefix: str
    # 明文 key：支持重复进来复制（老数据为 None，仅能看前缀）
    plain_key: str | None = None
    scopes: list[str]
    description: str | None
    scope_type: str = "app"
    scope_ref: str | None = None
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ApiKeyCreated(ApiKeyItem):
    """创建成功响应（plain_key 见基类）"""
