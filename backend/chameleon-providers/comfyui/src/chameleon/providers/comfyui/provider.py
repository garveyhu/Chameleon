"""ComfyuiProvider —— 把本地 ComfyUI 当作可对话生图 agent（文生图 + 图生图）

source='comfyui' 的 agent，其 AgentDef.config 存绑定的 image 模型：
    {"model_id": <image 类型 LLMModel.id>}
模型 defaults 同时配 t2i（workflow）与 i2i（edit_workflow）两个工作流。

stream(ctx) 流程：
  1. ctx → 提示词：取最后一条用户消息作为生图 prompt
  2. config.model_id → resolve_media_target → host + t2i/i2i 工作流 + 默认参数
  3. 意图路由（aikit langgraph）：判这轮文生图 / 图生图——
       - 有上传图，或历史有上一张生成图且判为"编辑" → i2i（用 edit_workflow + 输入图）
       - 否则 → t2i
  4. stream_generate 提交本地 ComfyUI：
       - submitted / progress → step（进度可见）
       - done → delta 推一段 Markdown 图片 ![](url)，前端聊天气泡直接渲染
  5. done：answer="" 让聚合器用 delta 累积（即 Markdown 图片）

不持久化生图产物表（trace 顶层 call_log 由 service 层写）；产物图已落 MinIO。
"""

from __future__ import annotations

import re
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


#: Markdown 图片语法 ![alt](url)；视频回答是 [▶...](url) 链接语法（无前导 !），不会被匹配
_IMG_MD = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def _prior_image_url(history: list[Message]) -> str | None:
    """从会话历史取最近一张生成图的 URL（图生图"延续编辑上一张"用）。

    生图 provider 历史回答形如 ``![image](url)``；逆序找最近一条 assistant 消息里的
    图片 URL，找不到返回 None。
    """
    for m in reversed(history):
        if m.role != "assistant":
            continue
        match = _IMG_MD.search(m.text())
        if match:
            return match.group(1).strip()
    return None


class ComfyuiProvider(Provider):
    """in-process 本地生图 provider（provider name = "comfyui"）"""

    name = "comfyui"

    async def stream(self, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        from dataclasses import replace

        from chameleon.aikit.tasks.media_intent import route_media_intent
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

        # 生成参数 / 上传图经 InvokeContext.options 透传（Playground 生成面板设置）
        opts = ctx.options or {}
        gen_params = opts.get("gen_params") or {}
        input_images = list(opts.get("input_images") or [])

        # ── 意图路由（langgraph）：判文生图 / 图生图，并定输入图来源 ────────────
        # 上传图优先；否则若判为"编辑上一张"，取会话历史里最近一张生成图作输入。
        prior_url = _prior_image_url(ctx.history or [])
        intent = await route_media_intent(
            prompt,
            has_uploaded=bool(input_images),
            has_prior=bool(prior_url),
        )
        mode_label = "文生图"
        if intent.task == "i2i" and target.edit_upstream:
            target = replace(target, upstream=target.edit_upstream)
            mode_label = "图生图"
            if not input_images and intent.use_prior and prior_url:
                input_images = [prior_url]
        elif intent.task == "i2i":
            # 判为图生图但模型没配 edit_workflow → 降级文生图（不中断出图）
            logger.warning(
                "comfyui agent {} 判为图生图但未配 edit_workflow，降级文生图",
                ctx.agent_def.key,
            )

        logger.debug(
            "comfyui provider | agent={} | mode={} | reason={} | upstream={} | prompt={!r}",
            ctx.agent_def.key,
            mode_label,
            intent.reason,
            target.upstream,
            prompt[:60],
        )

        yield StreamEvent(
            type=StreamEventType.step,
            data={"name": mode_label, "status": "running"},
        )

        start = time.monotonic()
        media_url = ""
        media_kind = "image"
        try:
            async for ev in stream_generate(
                target, prompt=prompt, params=gen_params, input_images=input_images
            ):
                if ev["type"] == "done":
                    media_url = ev["url"]
                    media_kind = ev.get("media_kind", "image")
        except Exception as e:
            yield StreamEvent(
                type=StreamEventType.step,
                data={
                    "name": mode_label,
                    "status": "failed",
                    "duration_ms": int((time.monotonic() - start) * 1000),
                },
            )
            yield StreamEvent(
                type=StreamEventType.error,
                data={"message": f"生成失败: {e}"},
            )
            return

        duration_ms = int((time.monotonic() - start) * 1000)
        yield StreamEvent(
            type=StreamEventType.step,
            data={"name": mode_label, "status": "success", "duration_ms": duration_ms},
        )

        if not media_url:
            yield StreamEvent(
                type=StreamEventType.error,
                data={"message": "未产出结果"},
            )
            return

        # 图片 → Markdown 图片（前端渲染 <img>）；视频 → Markdown 链接（点开播放）
        text = (
            f"[▶ 点击查看生成的视频]({media_url})"
            if media_kind == "video"
            else f"![image]({media_url})"
        )
        yield StreamEvent(type=StreamEventType.delta, data={"text": text})
        yield StreamEvent(
            type=StreamEventType.done,
            data={
                "answer": "",  # 用 delta 累积（Markdown 图片）
                "session_id": ctx.session_id,
                "request_id": ctx.request_id,
            },
        )
