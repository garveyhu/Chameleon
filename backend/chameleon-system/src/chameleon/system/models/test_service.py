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
from chameleon.core.components.llms.base import BaseLLM
from chameleon.core.embedding.openai_compat import OpenAICompatEmbedding
from chameleon.core.models import LLMModel, Provider
from chameleon.core.utils.crypto import get_or_decrypt

PING_PROMPT = "请用一句话简短自我介绍。"
DEFAULT_STREAM_MAX_TOKENS = 128


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
) -> AsyncIterator[dict]:
    """流式测试模型。

    chunk 类型：
      - {"meta": {"kind": "chat" | "embedding", "model": "...", "provider": "..."}}
      - {"delta": "..."}                  # 文本片段
      - {"end": True, "latency_ms": N, "usage": {...} | None, "sample": "..."}
      - {"error": {"type": "...", "message": "..."}}  # 错误（错误后不再有 end）
    """
    m, p = await _load_model_and_provider(session, model_id)

    yield {
        "meta": {
            "kind": m.kind,
            "model": m.code,
            "provider": p.code,
        }
    }

    if not p.base_url:
        yield {
            "error": {
                "type": "ConfigError",
                "message": f"provider {p.code} 未配置 base_url",
            }
        }
        return

    api_key = get_or_decrypt(p.api_key_encrypted) or ""
    start = time.monotonic()

    try:
        if m.kind == "chat":
            defaults = m.defaults or {}
            llm = BaseLLM(
                model=m.code,
                api_key=api_key,
                api_base=p.base_url,
                temperature=defaults.get("temperature", 0.7),
                max_tokens=defaults.get("max_tokens", DEFAULT_STREAM_MAX_TOKENS),
            )
            messages = [HumanMessage(content=prompt or PING_PROMPT)]
            collected: list[str] = []
            usage: dict | None = None
            async for chunk in llm.astream(messages):
                text = getattr(chunk, "content", None)
                if text:
                    collected.append(text)
                    yield {"delta": text}
                u = getattr(chunk, "usage_metadata", None)
                if u:
                    usage = {
                        "input_tokens": int(u.get("input_tokens") or 0),
                        "output_tokens": int(u.get("output_tokens") or 0),
                        "total_tokens": int(u.get("total_tokens") or 0),
                    }
            latency_ms = int((time.monotonic() - start) * 1000)
            sample = "".join(collected)[:120] or "(空回复)"
            yield {
                "end": True,
                "latency_ms": latency_ms,
                "usage": usage,
                "sample": sample,
            }
        elif m.kind == "embedding":
            dim = m.dim or 1536
            client = OpenAICompatEmbedding(
                base_url=p.base_url,
                api_key=api_key,
                model=m.code,
                dim=int(dim),
            )
            vectors = await client.embed(["hello"])
            latency_ms = int((time.monotonic() - start) * 1000)
            real_dim = len(vectors[0]) if vectors else 0
            preview = (
                ", ".join(f"{v:.4f}" for v in vectors[0][:5]) if vectors else ""
            )
            yield {"delta": f"vector[dim={real_dim}] 前 5 维: [{preview}, ...]\n"}
            yield {
                "end": True,
                "latency_ms": latency_ms,
                "usage": None,
                "sample": f"dim={real_dim}",
            }
        else:
            yield {
                "error": {
                    "type": "UnsupportedKind",
                    "message": f"未支持的 model.kind: {m.kind}",
                }
            }
    except Exception as e:  # noqa: BLE001
        logger.exception("stream model test failed | model_id={}", model_id)
        yield {
            "error": {
                "type": type(e).__name__,
                "message": str(e)[:300],
            }
        }
