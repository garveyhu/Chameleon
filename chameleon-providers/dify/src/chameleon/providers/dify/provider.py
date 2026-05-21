"""DifyProvider —— HTTP 外调 DIFY 编排平台

config 字段（来自 agents.yaml）：
  endpoint:     DIFY 实例地址（如 http://dify.local/v1）
  app_id:       仅记录用（DIFY chat 不需要在请求体；workflow 也由 api_key 隔离）
  api_key_env:  实际 api key 从 env 取，避免泄漏
  mode:         "chat" | "workflow"   —— 裁决 A14

双写：ctx.provider_conv_id 透传为 conversation_id；新建会话时 DIFY 返回 conv_id，
通过 metadata event → done event 写回 InvokeResult.provider_conv_id。
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from loguru import logger

from chameleon.core.config import inventory
from chameleon.core.api.exceptions import ProviderConfigError
from chameleon.providers.base.protocol import Provider
from chameleon.providers.base.types import (
    InvokeContext,
    StreamEvent,
    StreamEventType,
)
from chameleon.providers.dify.client import DifyClient
from chameleon.providers.dify.stream import translate_chat, translate_workflow


class DifyProvider(Provider):
    name = "dify"

    async def stream(self, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        cfg = ctx.agent_def.config
        endpoint = cfg.get("endpoint")
        api_key_env = cfg.get("api_key_env")
        mode = cfg.get("mode", "chat")

        if not endpoint or not api_key_env:
            raise ProviderConfigError(
                message=f"dify agent {ctx.agent_def.key} missing endpoint / api_key_env"
            )

        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise ProviderConfigError(
                message=f"env {api_key_env} not set for agent {ctx.agent_def.key}"
            )

        timeout_ms = inventory.provider_timeout_ms("dify")
        client = DifyClient(endpoint, api_key, timeout=timeout_ms / 1000)

        user = ctx.context_vars.get("user_id") or ctx.app_id

        if mode == "chat":
            query = _current_input_text(ctx)
            inputs = dict(ctx.options) if ctx.options else {}
            logger.debug(
                "dify chat | agent={} | conv_id={} | query_len={}",
                ctx.agent_def.key,
                ctx.provider_conv_id,
                len(query),
            )
            async for raw in client.stream_chat(
                query=query,
                conversation_id=ctx.provider_conv_id,
                user=user,
                inputs=inputs,
            ):
                for ev in translate_chat(raw):
                    yield ev
                    if ev.type == StreamEventType.error:
                        return

        elif mode == "workflow":
            # workflow 模式下 input 全走 inputs 字段；约定 ctx.input → "query" 字段
            workflow_inputs = dict(ctx.options) if ctx.options else {}
            workflow_inputs.setdefault("query", _current_input_text(ctx))
            logger.debug(
                "dify workflow | agent={} | inputs_keys={}",
                ctx.agent_def.key,
                list(workflow_inputs.keys()),
            )
            async for raw in client.stream_workflow(
                inputs=workflow_inputs,
                user=user,
            ):
                for ev in translate_workflow(raw):
                    yield ev
                    if ev.type == StreamEventType.error:
                        return

        else:
            raise ProviderConfigError(
                message=f"dify agent {ctx.agent_def.key} unknown mode: {mode}"
            )

    async def healthcheck(self) -> bool:
        # 外部 HTTP —— 实际探活会消耗 quota，v1 简化总是 True
        return True


def _current_input_text(ctx: InvokeContext) -> str:
    """取当前轮 query 文本（DIFY 不消费历史消息列表，只取最新 user query）"""
    if isinstance(ctx.input, str):
        return ctx.input
    # list[Message]：取最后一条 user
    for m in reversed(ctx.input):
        if m.role == "user":
            return m.content
    return ""
