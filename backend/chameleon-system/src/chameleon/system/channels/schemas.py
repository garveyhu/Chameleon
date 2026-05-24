"""channels DTO

入参 XxxRequest / 出参 XxxItem，命名遵循项目规约。
api_key 在出参用 has_api_key 暴露（明文绝不返回）。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from chameleon.core.models.channel import ChannelStatus


class ChannelItem(BaseModel):
    """channel 出参 —— 不含明文 api_key，密钥状态用 has_api_key 表达"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    provider_id: int
    provider_code: str | None = None  # join 时填，便于前端展示
    name: str
    has_api_key: bool = False
    # C7：多 key 池大小（只暴露数量，明文 key 绝不返回）
    key_count: int = 0
    base_url: str | None = None
    status: str
    weight: int
    priority: int
    response_time_ms: int | None = None
    fail_count: int
    used_quota: int
    last_failed_at: datetime | None = None
    last_success_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CreateChannelRequest(BaseModel):
    provider_id: int
    name: str = Field(min_length=1, max_length=64)
    api_key: str | None = None  # 明文，service 内加密落盘
    # C7：多 key 池（明文列表，service 内逐个加密）；非空则路由走轮转
    keys: list[str] | None = Field(default=None, description="多 key 池（明文）")
    base_url: str | None = Field(default=None, max_length=512)
    weight: int = Field(default=0, ge=0)
    priority: int = Field(default=0, ge=0)


class UpdateChannelRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    # 非空才更新 api_key；显式传 ""（空字符串）表示清空
    api_key: str | None = Field(
        default=None,
        description="非空才更新；空字符串 → 清空",
    )
    # C7：非 None 才更新 key 池；传 [] 清空池（回退单 key）
    keys: list[str] | None = Field(
        default=None, description="非 None 才更新；[] 清空池"
    )
    base_url: str | None = Field(default=None, max_length=512)
    status: str | None = Field(
        default=None,
        description=f"取值：{[s.value for s in ChannelStatus]}",
    )
    weight: int | None = Field(default=None, ge=0)
    priority: int | None = Field(default=None, ge=0)


class ChannelHealthItem(BaseModel):
    """channel 健康快照（实时从 channel 行算出来；call_logs 后续做 1h 聚合）"""

    channel_id: int
    status: str
    fail_count: int
    response_time_ms: int | None = None
    last_failed_at: datetime | None = None
    last_success_at: datetime | None = None
    used_quota: int
