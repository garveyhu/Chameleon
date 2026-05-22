"""models HTTP 路由 (/v1/admin/models)"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.core.api.response import Result
from chameleon.core.api.sse import sse_response
from chameleon.core.components.llms.base import BaseLLM
from chameleon.core.components.llms.factory import reload_llm_cache
from chameleon.core.embedding.openai_compat import OpenAICompatEmbedding
from chameleon.core.infra.db import get_session
from chameleon.core.models import LLMModel, Provider
from chameleon.core.utils.crypto import get_or_decrypt
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.models import test_service


class ModelItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider_id: int
    provider_code: str | None = None
    code: str
    kind: str
    dim: int | None = None
    defaults: dict | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class CreateModelRequest(BaseModel):
    provider_id: int
    code: str = Field(min_length=1, max_length=128)
    kind: str = Field(pattern="^(chat|embedding)$")
    dim: int | None = None
    defaults: dict | None = None


class UpdateModelRequest(BaseModel):
    dim: int | None = None
    defaults: dict | None = None
    enabled: bool | None = None


def _to_item(m: LLMModel, provider_code: str | None = None) -> ModelItem:
    return ModelItem(
        id=m.id,
        provider_id=m.provider_id,
        provider_code=provider_code,
        code=m.code,
        kind=m.kind,
        dim=m.dim,
        defaults=m.defaults,
        enabled=m.enabled,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


router = APIRouter(prefix="/v1/admin/models", tags=["admin:models"])


@router.get("", response_model=Result[list[ModelItem]])
async def list_models(
    kind: str | None = Query(default=None, pattern="^(chat|embedding)$"),
    provider_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("models:read")),
) -> Result[list[ModelItem]]:
    stmt = (
        select(LLMModel, Provider.code)
        .join(Provider, LLMModel.provider_id == Provider.id)
        .where(LLMModel.deleted_at.is_(None))
        .order_by(LLMModel.kind, LLMModel.code)
    )
    if kind:
        stmt = stmt.where(LLMModel.kind == kind)
    if provider_id:
        stmt = stmt.where(LLMModel.provider_id == provider_id)
    rows = (await session.execute(stmt)).all()
    return Result.ok([_to_item(m, pcode) for m, pcode in rows])


@router.post("", response_model=Result[ModelItem])
async def create_model(
    req: CreateModelRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("models:write")),
) -> Result[ModelItem]:
    provider = (
        await session.execute(
            select(Provider).where(
                Provider.id == req.provider_id, Provider.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if provider is None:
        raise ValidationError(message=f"provider 不存在: {req.provider_id}")

    existing = (
        await session.execute(
            select(LLMModel).where(
                LLMModel.provider_id == req.provider_id,
                LLMModel.code == req.code,
                LLMModel.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ValidationError(message=f"同 provider 已有同 code 的 model: {req.code}")

    m = LLMModel(
        provider_id=req.provider_id,
        code=req.code,
        kind=req.kind,
        dim=req.dim,
        defaults=req.defaults,
        enabled=True,
    )
    session.add(m)
    await session.flush()
    await session.commit()
    await reload_llm_cache()
    return Result.ok(_to_item(m, provider.code))


@router.post("/{model_id}/update", response_model=Result[ModelItem])
async def update_model(
    model_id: int,
    req: UpdateModelRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("models:write")),
) -> Result[ModelItem]:
    m = (
        await session.execute(
            select(LLMModel).where(
                LLMModel.id == model_id, LLMModel.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if m is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"model 不存在: {model_id}"
        )
    if req.dim is not None:
        m.dim = req.dim
    if req.defaults is not None:
        m.defaults = req.defaults
    if req.enabled is not None:
        m.enabled = req.enabled
    await session.flush()
    await session.commit()
    await reload_llm_cache()
    return Result.ok(_to_item(m))


class TestModelResult(BaseModel):
    ok: bool
    latency_ms: int
    sample: str
    detail: str


@router.post("/{model_id}/test", response_model=Result[TestModelResult])
async def test_model(
    model_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("models:read")),
) -> Result[TestModelResult]:
    """对指定 model 发一个最小请求验证可用性

    - chat: chat("ping") max_tokens=5，返回首段文本
    - embedding: embed(["hello"]) 返回 dim
    """
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
    m, p = row

    if not p.base_url:
        return Result.ok(
            TestModelResult(ok=False, latency_ms=0, sample="", detail="provider.base_url 未配置")
        )

    api_key = get_or_decrypt(p.api_key_encrypted) or ""
    start = time.monotonic()
    try:
        if m.kind == "chat":
            defaults = m.defaults or {}
            client = BaseLLM(
                model=m.code,
                api_key=api_key,
                api_base=p.base_url,
                temperature=defaults.get("temperature", 0.7),
                max_tokens=5,
            )
            resp = await client.ainvoke("ping")
            content = getattr(resp, "content", "") or ""
            sample = str(content)[:60] if content else "(空回复)"
        elif m.kind == "embedding":
            dim = m.dim or 1536
            client = OpenAICompatEmbedding(
                base_url=p.base_url,
                api_key=api_key,
                model=m.code,
                dim=int(dim),
            )
            vectors = await client.embed(["hello"])
            sample = f"vector[dim={len(vectors[0])}]"
        else:
            return Result.ok(
                TestModelResult(
                    ok=False, latency_ms=0, sample="", detail=f"未支持的 kind: {m.kind}"
                )
            )
        latency_ms = int((time.monotonic() - start) * 1000)
        return Result.ok(
            TestModelResult(
                ok=True,
                latency_ms=latency_ms,
                sample=sample,
                detail=f"延迟 {latency_ms}ms · 回包: {sample!r}",
            )
        )
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.exception("model test failed: {} (model_id={})", e, model_id)
        return Result.ok(
            TestModelResult(
                ok=False,
                latency_ms=latency_ms,
                sample="",
                detail=f"{type(e).__name__}: {e}",
            )
        )


class StreamTestRequest(BaseModel):
    prompt: str | None = Field(default=None, max_length=2000)


@router.post("/{model_id}/test/stream")
async def test_model_stream(
    model_id: int,
    req: StreamTestRequest | None = None,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("models:read")),
):
    """SSE 流式测试：chat 模型逐 token 推；embedding 一次性返回 dim + 预览。

    chunk 结构详见 test_service.stream_test 注释。
    """
    prompt = req.prompt if req else None
    return sse_response(
        test_service.stream_test(session, model_id=model_id, prompt=prompt),
        log_label=f"model_test:{model_id}",
    )


@router.post("/{model_id}/delete", response_model=Result[None])
async def delete_model(
    model_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("models:delete")),
) -> Result[None]:
    m = (
        await session.execute(
            select(LLMModel).where(
                LLMModel.id == model_id, LLMModel.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if m is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"model 不存在: {model_id}"
        )
    m.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    await session.commit()
    await reload_llm_cache()
    return Result.ok(None)
