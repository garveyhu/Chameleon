"""ComfyuiProvider —— 把本地 ComfyUI 文生图当作可对话 agent

source='comfyui' 的 agent，其 AgentDef.config 存绑定的 image 模型：
    {"model_id": <image 类型 LLMModel.id>}

stream(ctx) 流程：
  1. ctx → 提示词：取最后一条用户消息作为生图 prompt
  2. config.model_id → resolve_image_target → host + 工作流 + 默认参数
  3. stream_generate 提交本地 ComfyUI：
       - submitted / progress → step（进度可见）
       - done → delta 推一段 Markdown 图片 ![](url)，前端聊天气泡直接渲染
  4. done：answer="" 让聚合器用 delta 累积（即 Markdown 图片）

不持久化生图产物表（trace 顶层 call_log 由 service 层写）；产物图已落 MinIO。
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

from loguru import logger

from chameleon.core.api.exceptions import ProviderInternalError, RegistryError
from chameleon.providers.base.protocol import Provider
from chameleon.providers.base.types import (
    InvokeContext,
    Message,
    StreamEvent,
    StreamEventType,
)

#: 用户未给提示词时的兜底（极少触发，避免空 prompt 让 ComfyUI 出纯噪声图）
_FALLBACK_PROMPT = "a serene landscape, soft light, highly detailed"


def _extract_prompt(ctx: InvokeContext) -> str:
    """从 ctx 取「当前用户消息」作为生图提示词。"""
    if isinstance(ctx.input, str):
        return ctx.input.strip()
    msgs: list[Message] = ctx.input
    return msgs[-1].text().strip() if msgs else ""


class ComfyuiProvider(Provider):
    """in-process 本地生图 provider（provider name = "comfyui"）"""

    name = "comfyui"

    async def stream(self, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        from chameleon.integrations.mediagen import (
            MediaConfigError,
            resolve_media_target,
            stream_generate,
        )

        model_id = ctx.agent_def.config.get("model_id")
        if not model_id:
            raise RegistryError(
                message=(
                    f"comfyui agent {ctx.agent_def.key} 未绑定生图模型"
                    "（config.model_id 缺失）"
                )
            )

        try:
            target = await resolve_media_target(int(model_id))
        except MediaConfigError as e:
            raise ProviderInternalError(
                message=f"comfyui agent {ctx.agent_def.key} 生图模型配置无效: {e}"
            ) from e

        prompt = _extract_prompt(ctx) or _FALLBACK_PROMPT
        logger.debug(
            "comfyui provider | agent={} | model={} | driver={} | upstream={} | prompt={!r}",
            ctx.agent_def.key,
            target.model_code,
            target.driver,
            target.upstream,
            prompt[:60],
        )

        yield StreamEvent(
            type=StreamEventType.step,
            data={"name": "生图", "status": "running"},
        )

        start = time.monotonic()
        image_url = ""
        try:
            async for ev in stream_generate(target, prompt=prompt):
                if ev["type"] == "done":
                    image_url = ev["url"]
        except Exception as e:
            yield StreamEvent(
                type=StreamEventType.step,
                data={
                    "name": "生图",
                    "status": "failed",
                    "duration_ms": int((time.monotonic() - start) * 1000),
                },
            )
            yield StreamEvent(
                type=StreamEventType.error,
                data={"message": f"生图失败: {e}"},
            )
            return

        duration_ms = int((time.monotonic() - start) * 1000)
        yield StreamEvent(
            type=StreamEventType.step,
            data={"name": "生图", "status": "success", "duration_ms": duration_ms},
        )

        if not image_url:
            yield StreamEvent(
                type=StreamEventType.error,
                data={"message": "ComfyUI 未产出图片"},
            )
            return

        # Markdown 图片走 delta：前端聊天气泡按 Markdown 渲染为 <img>
        yield StreamEvent(
            type=StreamEventType.delta,
            data={"text": f"![image]({image_url})"},
        )
        yield StreamEvent(
            type=StreamEventType.done,
            data={
                "answer": "",  # 用 delta 累积（Markdown 图片）
                "session_id": ctx.session_id,
                "request_id": ctx.request_id,
            },
        )
