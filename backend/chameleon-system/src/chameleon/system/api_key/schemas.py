"""api_key 模块 DTO（Pydantic）

设计：
- ApiKeyItem: 列表/详情用，绝不含明文 key、绝不含 hash
- ApiKeyCreated: 创建响应，含 plain_key（仅一次回显）
- CreateApiKeyRequest: 创建入参
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateApiKeyRequest(BaseModel):
    # app_id：自由「调用方/来源标签」，可选；不传则服务端用 name 的 slug 兜底
    app_id: str | None = Field(
        default=None, max_length=64, description="调用方/来源标签（可选）"
    )
    name: str = Field(..., min_length=1, max_length=128, description="可读名称")
    scopes: list[str] = Field(default_factory=list, description='["admin"] 或 []')
    description: str | None = None
    # 作用域：global（通吃）/ app（某智能体/应用）/ kb（某知识库）
    scope_type: str = Field(default="global", pattern="^(global|app|kb)$")
    scope_ref: str | None = Field(
        None, description="域内目标：app→agent_key、kb→kb_key、global→空"
    )
    # 配额（可选，仅落字段暂不 enforce）
    qpm_limit: int | None = Field(default=None, ge=0)
    qpd_limit: int | None = Field(default=None, ge=0)


class ApiKeyItem(BaseModel):
    id: int
    app_id: str
    name: str
    key_prefix: str
    # 明文 key：支持重复进来复制（老数据为 None，仅能看前缀）
    plain_key: str | None = None
    scopes: list[str]
    description: str | None
    scope_type: str = "global"
    scope_ref: str | None = None
    qpm_limit: int | None = None
    qpd_limit: int | None = None
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ApiKeyCreated(ApiKeyItem):
    """创建成功响应（plain_key 见基类）"""
