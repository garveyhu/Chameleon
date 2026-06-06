"""ImageGenNode —— 工作流里的「生图」节点（本地 ComfyUI 文生图）

data 配置：
    {
      "model_id": 123,            # 必填；image 类型 LLMModel.id（绑定 host + 工作流）
      "prompt": "{{#sys.query#}}", # 可选；支持 {{#var#}} 引用，缺省取 input 的 query
      "params": {"width": 768}    # 可选；覆盖模型 defaults 里的工作流参数
    }

input：上游 dict（含 query/question/prompt 等字段）/ 字符串。

output：
    {
      "image_url": "https://minio/...",   # 产物 presigned URL
      "image_key": "imagegen/.../x.png",  # MinIO object key
      "answer": "![image](url)",          # Markdown 图片（作答案节点时直接渲染）
      "prompt": "...",                    # 实际使用的提示词
      "model": "z-image-turbo",
      "workflow": "zimage_t2i",
      "latency_ms": 61800,
    }

流式：execute_stream 在 emit 非空时，于产出后推一段 Markdown 图片片段——这样当本
节点作为 graph-agent 的答案节点时，图片以 delta 形式流入会话直接渲染。生成过程
本身不流式（diffusion 是「提交→等待→取图」），进度由节点 started/finished step 体现。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from chameleon.engine.graph.context import NodeContext
from chameleon.engine.graph.node_base import DeltaSink, Node
from chameleon.engine.graph.registry import register_node_type
from chameleon.engine.graph.variables import resolve_in_text

#: 从 input dict 取提示词的候选字段（与 LLMNode 对齐）
_PROMPT_KEYS = ("prompt", "query", "question", "input", "text")


def _pick_prompt(input: Any, node_vars: dict[str, Any], data: dict[str, Any]) -> str:
    """决定本次生图的提示词：data.prompt（含变量引用）优先，否则取 input 字段。"""
    raw = data.get("prompt")
    if isinstance(raw, str) and raw.strip():
        resolved = resolve_in_text(raw, node_vars).strip()
        if resolved:
            return resolved
    if isinstance(input, str):
        return input.strip()
    if isinstance(input, dict):
        for k in _PROMPT_KEYS:
            v = input.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    sys_vars = node_vars.get("sys") or {}
    return str(sys_vars.get("query") or "").strip()


class ImageGenNode(Node[Any, dict]):
    """本地 ComfyUI 文生图节点。"""

    type = "image_gen"

    def validate_data(self, data: dict[str, Any]) -> None:
        model_id = data.get("model_id")
        if model_id is None:
            raise ValueError("ImageGenNode.data.model_id 必填（image 模型 id）")
        try:
            int(model_id)
        except (TypeError, ValueError) as e:
            raise ValueError("ImageGenNode.data.model_id 必须是整数") from e
        params = data.get("params")
        if params is not None and not isinstance(params, dict):
            raise ValueError("ImageGenNode.data.params 必须是对象")

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        return await self._run(ctx, input, emit=None)

    async def execute_stream(
        self, ctx: NodeContext, input: Any, emit: DeltaSink | None
    ) -> dict:
        return await self._run(ctx, input, emit=emit)

    async def _run(
        self, ctx: NodeContext, input: Any, emit: DeltaSink | None
    ) -> dict:
        from chameleon.integrations.images import (
            ImageConfigError,
            resolve_image_target,
            stream_generate,
        )

        data = self.spec.data
        node_vars = (ctx.extra or {}).get("__vars__") or {}
        prompt = _pick_prompt(input, node_vars, data)
        if not prompt:
            raise ValueError("ImageGenNode 无可用提示词（data.prompt / input.query 均空）")

        try:
            target = await resolve_image_target(int(data["model_id"]))
        except ImageConfigError as e:
            raise ValueError(f"生图模型配置无效: {e}") from e

        params = {**target.params, **(data.get("params") or {})}
        logger.debug(
            "ImageGenNode {} | model={} | workflow={} | prompt={!r}",
            self.id,
            target.model_code,
            target.workflow_id,
            prompt[:60],
        )

        image_url = ""
        image_key = ""
        latency_ms = 0
        async for ev in stream_generate(
            host=target.host,
            workflow_id=target.workflow_id,
            prompt=prompt,
            params=params,
        ):
            if ev["type"] == "done":
                image_url = ev["image_url"]
                image_key = ev["image_key"]
                latency_ms = ev["latency_ms"]

        if not image_url:
            raise ValueError("ComfyUI 未产出图片")

        answer = f"![image]({image_url})"
        if emit is not None:
            await emit(answer)

        return {
            "image_url": image_url,
            "image_key": image_key,
            "answer": answer,
            "prompt": prompt,
            "model": target.model_code,
            "workflow": target.workflow_id,
            "latency_ms": latency_ms,
        }


register_node_type(ImageGenNode)
