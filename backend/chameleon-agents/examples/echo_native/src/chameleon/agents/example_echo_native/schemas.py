"""Echo agent 入参 schema

注册到 chameleon.core.schema registry，供 admin 前端 / playground 在
调 echo agent 时动态渲染输入表单。

`agent.input.{agent_key}` 命名约定让前端按 agent_key 一对一查 schema。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from chameleon.core.schema import register


@register("agent.example-echo-native.input")
class EchoAgentInput(BaseModel):
    """Echo agent 入参（所有 example-echo-* agent 共享同一入参形状）"""

    input: str = Field(
        ...,
        description="要回声的文本；含 'doc:<kb_key>' 会触发 RAG 检索对应 KB",
        min_length=1,
        max_length=8000,
        json_schema_extra={
            "format": "textarea",
            "placeholder": "请输入你想 echo 的内容…",
        },
    )
