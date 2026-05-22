"""DIFY provider 的 agent config schema

注册到 chameleon.core.schema registry，供 admin 前端在创建 / 编辑
source=dify 的 agent 时动态渲染表单。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from chameleon.core.schema import register


@register("provider.dify.agent_config")
class DifyAgentConfig(BaseModel):
    """DIFY 外部 agent 配置

    实际 API key 从 env 取（api_key_env 字段指定 env 变量名），避免明文落 DB。
    """

    endpoint: str = Field(
        ...,
        description="DIFY 实例地址，如 https://api.dify.ai/v1",
        json_schema_extra={"format": "uri", "placeholder": "https://api.dify.ai/v1"},
    )
    api_key_env: str = Field(
        ...,
        description="环境变量名（不是 API Key 本身）；运行时由 os.environ 解析",
        min_length=1,
        max_length=128,
        json_schema_extra={"placeholder": "DIFY_API_KEY_FOO"},
    )
    mode: Literal["chat", "workflow"] = Field(
        "chat",
        description="DIFY 应用模式：chat（对话）或 workflow（工作流）",
    )
    app_id: str | None = Field(
        None,
        description="可选：仅供运维标记；DIFY 实际靠 api_key 隔离 app",
        max_length=64,
    )
