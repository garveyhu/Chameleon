"""模型连通性测试 service。

- one-shot: 一次请求拿结果（embedding / 不需要流式的场景）
- streaming: chat 模型走 LLM.astream，逐 token yield {"delta": str}；末尾 {"end": True, "usage": ...}

所有外部调用异常都会被捕获并以 {"error": {...}} chunk 形式返回，由 API 层包成 SSE。
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

from langchain_core.messages import HumanMessage
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.api.sse_events import (
    ImageChunkPayload,
    UsagePayload,
    VideoChunkPayload,
    event_delta,
    event_end,
    event_error,
    event_image_chunk,
    event_meta,
    event_video_chunk,
)
from chameleon.data.models import LLMModel, Provider
from chameleon.integrations.embedding.openai_compat import OpenAICompatEmbedding
from chameleon.integrations.llms.base import BaseLLM
from chameleon.integrations.llms.factory import resolve_upstream
from chameleon.integrations.mediagen import (
    MediaConfigError,
    build_media_target,
    stream_generate,
)
from chameleon.integrations.rerank.openai_compat import OpenAICompatReranker

PING_PROMPT = "请用一句话简短自我介绍。"
# 连通性测试上限放宽：推理模型（如 Qwen3 thinking）一轮思考就可能吃掉上千
# token，额度太小会导致 reasoning 占满、正式 content 一个字都没产出 → 空回复。
DEFAULT_STREAM_MAX_TOKENS = 2048
# image 模型连通性测试的默认提示词（用户未输入时）
DEFAULT_TEST_IMAGE_PROMPT = (
    "a cute corgi puppy running on green grass, sunny day, photorealistic"
)


async def _load_model_and_provider(
    session: AsyncSession, model_id: int
) -> tuple[LLMModel, Provider]:
    row = (
        await session.execute(
            select(LLMModel, Provider)
            .join(Provider, LLMModel.provider_id == Provider.id)
            .where(LLMModel.id == model_id, LLMModel.deleted_at.is_(None))
        )
    ).first()
    if row is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"model 不存在: {model_id}"
        )
    return row[0], row[1]


async def stream_test(
    session: AsyncSession,
    *,
    model_id: int,
    prompt: str | None = None,
    params: dict | None = None,
    input_images: list[str] | None = None,
) -> AsyncIterator[dict]:
    """流式测试模型。

    chunk 类型：
      - {"meta": {"kind": "chat" | "embedding", "model": "...", "provider": "..."}}
      - {"delta": "..."}                  # 文本片段
      - {"end": True, "latency_ms": N, "usage": {...} | None, "sample": "..."}
      - {"error": {"type": "...", "message": "..."}}  # 错误（错误后不再有 end）
    """
    m, p = await _load_model_and_provider(session, model_id)

    # 与工厂同口径解析有效上游（newapi 模式走网关）
    base_url, api_key, upstream_model = await resolve_upstream(session, m, p)
    yield event_meta(kind=m.kind, model=upstream_model, provider=p.code)

    if not base_url:
        yield event_error("ConfigError", f"provider {p.code} 未配置 base_url")
        return

    start = time.monotonic()

    try:
        if m.kind == "chat":
            defaults = m.defaults or {}
            llm = BaseLLM(
                model=upstream_model,
                api_key=api_key,
                api_base=base_url,
                temperature=defaults.get("temperature", 0.7),
                max_tokens=defaults.get("max_tokens", DEFAULT_STREAM_MAX_TOKENS),
            )
            messages = [HumanMessage(content=prompt or PING_PROMPT)]
            collected: list[str] = []
            usage: UsagePayload | None = None
            async for chunk in llm.astream(messages):
                text = getattr(chunk, "content", None)
                if text:
                    collected.append(text)
                    yield event_delta(text)
                u = getattr(chunk, "usage_metadata", None)
                if u:
                    usage = UsagePayload.from_dict(u)
            latency_ms = int((time.monotonic() - start) * 1000)
            text = "".join(collected)[:120]
            if text:
                sample = text
            elif usage and usage.output_tokens:
                # 消耗了 token 却无正式 content：典型推理模型——思考过程
                # （reasoning_content）占满 max_tokens，正式回答没轮到就被截断
                sample = (
                    f"(空回复：消耗 {usage.output_tokens} token 但无正式输出，"
                    "疑似推理模型思考占满额度，请调大该模型 max_tokens)"
                )
            else:
                sample = "(空回复)"
            yield event_end(usage=usage, latency_ms=latency_ms, sample=sample)
        elif m.kind == "embedding":
            dim = m.dim or 1536
            client = OpenAICompatEmbedding(
                base_url=base_url,
                api_key=api_key,
                model=upstream_model,
                dim=int(dim),
            )
            vectors = await client.embed(["hello"])
            latency_ms = int((time.monotonic() - start) * 1000)
            real_dim = len(vectors[0]) if vectors else 0
            preview = (
                ", ".join(f"{v:.4f}" for v in vectors[0][:5]) if vectors else ""
            )
            yield event_delta(
                f"vector[dim={real_dim}] 前 5 维: [{preview}, ...]\n"
            )
            yield event_end(
                usage=None, latency_ms=latency_ms, sample=f"dim={real_dim}"
            )
        elif m.kind == "rerank":
            reranker = OpenAICompatReranker(
                base_url=base_url,
                api_key=api_key,
                model=upstream_model,
                model_code=m.code,
            )
            results = await reranker.rerank(
                "什么是机器学习？",
                ["机器学习是人工智能的一个分支。", "今天天气晴朗，适合出门散步。"],
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            if results:
                ranking = "、".join(
                    f"#{r.index}={r.score:.4f}"
                    for r in sorted(results, key=lambda r: r.score, reverse=True)
                )
                top = max(results, key=lambda r: r.score)
                yield event_delta(
                    f"重排得分: {ranking}\n命中 #{top.index}（应为机器学习文档）\n"
                )
                sample = f"top#{top.index} {top.score:.4f}"
            else:
                yield event_delta("(空结果)\n")
                sample = "(空)"
            yield event_end(usage=None, latency_ms=latency_ms, sample=sample)
        elif m.kind in ("image", "video"):
            try:
                target = build_media_target(m, p)
            except MediaConfigError as e:
                yield event_error("ConfigError", str(e))
                return
            is_video = m.kind == "video"
            test_prompt = prompt or ("" if is_video else DEFAULT_TEST_IMAGE_PROMPT)
            yield event_delta(f"使用「{target.upstream}」（{target.driver}）提交生成…\n")
            out_url: str | None = None
            last_notice = 0
            try:
                gen = stream_generate(
                    target,
                    prompt=test_prompt,
                    params=params or {},
                    input_images=input_images or [],
                )
                async for ev in gen:
                    etype = ev["type"]
                    if etype == "submitted":
                        yield event_delta(
                            f"已提交（ref={ev['ref']}），生成中"
                            f"（{'视频通常数分钟' if is_video else '首次含模型加载可能数分钟'}）…\n"
                        )
                    elif etype == "progress":
                        secs = ev["elapsed_ms"] // 1000
                        if secs - last_notice >= 10:
                            last_notice = secs
                            yield event_delta(f"⏳ 已等待 {secs}s…\n")
                    elif etype == "done":
                        out_url = ev["url"]
                        if is_video:
                            yield event_video_chunk(
                                VideoChunkPayload(
                                    url=out_url, mime_type=ev.get("mime_type", "video/mp4")
                                )
                            )
                        else:
                            yield event_image_chunk(
                                ImageChunkPayload(
                                    url=out_url,
                                    detail="final",
                                    mime_type=ev.get("mime_type", "image/png"),
                                )
                            )
            except MediaConfigError as e:
                yield event_error("ConfigError", str(e))
                return
            latency_ms = int((time.monotonic() - start) * 1000)
            yield event_end(
                usage=None,
                latency_ms=latency_ms,
                sample=("生成成功" if out_url else "(无产物)"),
            )
        else:
            yield event_error("UnsupportedKind", f"未支持的 model.kind: {m.kind}")
    except Exception as e:  # noqa: BLE001
        logger.exception("stream model test failed | model_id={}", model_id)
        yield event_error(e)
