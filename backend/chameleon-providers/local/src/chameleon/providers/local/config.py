"""Local provider 的 agent config schema

local provider 调进程内的 BaseAgent 子类，所以 config 是定位类的 import path。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from chameleon.core.schema import register


@register("provider.local.agent_config")
class LocalAgentConfig(BaseModel):
    """本地 in-process agent 定位信息

    config.module + config.agent_class 一起定位到 BaseAgent 子类；
    LocalProvider 在 invoke 时 importlib + getattr 拿到类再调 .astream(ctx)。
    """

    module: str = Field(
        ...,
        description="Python 模块导入路径，如 chameleon.agents.example_echo_native.agent",
        min_length=1,
        max_length=256,
        json_schema_extra={
            "placeholder": "chameleon.agents.example_echo_native.agent",
        },
    )
    agent_class: str = Field(
        ...,
        description="模块中的类名（BaseAgent 子类）",
        min_length=1,
        max_length=128,
        json_schema_extra={"placeholder": "EchoNativeAgent"},
    )
