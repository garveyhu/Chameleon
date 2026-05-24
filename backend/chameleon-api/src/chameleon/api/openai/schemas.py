"""OpenAI 兼容 /v1/chat/completions 的请求/响应 DTO（够用子集）"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OAMessage(BaseModel):
    role: str
    content: str
    model_config = ConfigDict(extra="ignore")


class OAChatRequest(BaseModel):
    """OpenAI chat.completions 请求子集。

    model 字段当作 agent_key（与 FastGPT 一致：model 即应用标识）。
    """

    model: str = Field(description="agent_key（OpenAI 客户端的 model 字段）")
    messages: list[OAMessage]
    stream: bool = False
    # 多轮会话：可选，缺省每次新建（无状态）
    session_id: str | None = None

    model_config = ConfigDict(extra="ignore")
