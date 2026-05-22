"""FastGPTProvider —— OpenAI 兼容协议外调

config 字段：
  endpoint:     FastGPT 实例地址（如 http://fastgpt.local/api）
  api_key_env:  api key 名（实值走 env）
  app_id:       仅记录（OpenAI 协议靠 api_key 隔离 app）

ctx.provider_conv_id 透传为 chatId（裁决 A15 双写）。
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from loguru import logger

from chameleon.core.api.exceptions import ProviderConfigError
from chameleon.core.config import inventory
from chameleon.providers.base.protocol import Provider
from chameleon.providers.base.types import (
    InvokeContext,
    Message,
    StreamEvent,
    StreamEventType,
)
from chameleon.providers.fastgpt.client import FastGPTClient
from chameleon.providers.fastgpt.stream import translate


class FastGPTProvider(Provider):
    name = "fastgpt"

    async def stream(self, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        cfg = ctx.agent_def.config

        # P17.A2: 优先 channel_override（矩阵路由），fallback 老 agent.config 路径
        if ctx.channel_override is not None:
            endpoint = ctx.channel_override.base_url or cfg.get("endpoint")
            api_key = ctx.channel_override.api_key
            if not endpoint or not api_key:
                raise ProviderConfigError(
                    message=(
                        f"fastgpt channel #{ctx.channel_override.channel_id} 缺 "
                        "base_url / api_key（请在 admin /channels 配置）"
                    )
                )
        else:
            endpoint = cfg.get("endpoint")
            api_key_env = cfg.get("api_key_env")
            if not endpoint or not api_key_env:
                raise ProviderConfigError(
                    message=(
                        f"fastgpt agent {ctx.agent_def.key} missing endpoint / api_key_env"
                    )
                )
            api_key = os.environ.get(api_key_env)
            if not api_key:
                raise ProviderConfigError(
                    message=f"env {api_key_env} not set for agent {ctx.agent_def.key}"
                )

        timeout_ms = inventory.provider_timeout_ms("fastgpt")
        client = FastGPTClient(endpoint, api_key, timeout=timeout_ms / 1000)

        messages = _build_messages(ctx)
        variables = dict(ctx.options) if ctx.options else None

        logger.debug(
            "fastgpt chat | agent={} | chatId={} | messages={}",
            ctx.agent_def.key,
            ctx.provider_conv_id,
            len(messages),
        )

        # provider_conv_id 透传为 chatId（双写）
        # 注意：FastGPT 没有像 DIFY 那样在响应里返回新建的 chatId；
        # 这意味着如果 client 不传 chatId，FastGPT 自管会话但 Chameleon 拿不到映射。
        # 策略：当客户端未传 conv_id 时，service 层应预生成一个 chatId 传入（在 P3 service.invoke 处理）。
        async for raw in client.stream_chat(
            messages=messages,
            chat_id=ctx.provider_conv_id,
            variables=variables,
        ):
            for ev in translate(raw):
                yield ev
                if ev.type == StreamEventType.error:
                    return

    async def healthcheck(self) -> bool:
        return True


def _build_messages(ctx: InvokeContext) -> list[dict]:
    """ctx.history + 当前 input → OpenAI 兼容 messages 数组"""
    msgs = [_msg_to_dict(m) for m in ctx.history]
    if isinstance(ctx.input, str):
        msgs.append({"role": "user", "content": ctx.input})
    else:
        msgs.extend(_msg_to_dict(m) for m in ctx.input)
    return msgs


def _msg_to_dict(m: Message) -> dict:
    d: dict = {"role": m.role, "content": m.content}
    if m.name:
        d["name"] = m.name
    if m.tool_call_id:
        d["tool_call_id"] = m.tool_call_id
    return d
