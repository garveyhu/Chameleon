"""FastGPT provider 的 agent config schema

注册到 chameleon.core.schema registry，供 admin 前端在创建 / 编辑
source=fastgpt 的 agent 时动态渲染表单。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from chameleon.core.schema import register


@register("provider.fastgpt.agent_config")
class FastGPTAgentConfig(BaseModel):
    """FastGPT 外部 agent 配置（OpenAI 兼容协议）

    实际 API key 从 env 取（api_key_env 字段指定 env 变量名），避免明文落 DB。
    """

    endpoint: str = Field(
        ...,
        description="FastGPT 实例 OpenAI 兼容 API 入口，如 http://fastgpt.local/api",
        json_schema_extra={"format": "uri", "placeholder": "http://fastgpt.local/api"},
    )
    api_key_env: str = Field(
        ...,
        description="环境变量名（不是 API Key 本身）；运行时由 os.environ 解析",
        min_length=1,
        max_length=128,
        json_schema_extra={"placeholder": "FASTGPT_API_KEY_FOO"},
    )
    app_id: str | None = Field(
        None,
        description="可选：仅供运维标记；FastGPT 实际靠 api_key 隔离 app",
        max_length=64,
    )
