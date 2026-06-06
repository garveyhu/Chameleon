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
from chameleon.data.infra.db import get_session
from chameleon.data.models import LLMModel, Provider
from chameleon.integrations.embedding.factory import reload_embedding_cache
from chameleon.integrations.embedding.openai_compat import OpenAICompatEmbedding
from chameleon.integrations.llms.base import BaseLLM
from chameleon.integrations.llms.factory import reload_llm_cache, resolve_upstream
from chameleon.integrations.rerank.factory import reload_rerank_cache
from chameleon.integrations.rerank.openai_compat import OpenAICompatReranker
from chameleon.system.audit_logs import write_audit_log
from chameleon.system.audit_logs.context import AuditContext, get_audit_context
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
    upstream_name: str | None = None
    capabilities: dict | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class CreateModelRequest(BaseModel):
    provider_id: int
    code: str = Field(min_length=1, max_length=128)
    kind: str = Field(pattern="^(chat|embedding|rerank|image|video)$")
    dim: int | None = None
    defaults: dict | None = None
    upstream_name: str | None = Field(default=None, max_length=128)
    capabilities: dict | None = None


class UpdateModelRequest(BaseModel):
    provider_id: int | None = None
    code: str | None = Field(default=None, min_length=1, max_length=128)
    dim: int | None = None
    defaults: dict | None = None
    enabled: bool | None = None
    upstream_name: str | None = None
    capabilities: dict | None = None


def _to_item(m: LLMModel, provider_code: str | None = None) -> ModelItem:
    return ModelItem(
        id=m.id,
        provider_id=m.provider_id,
        provider_code=provider_code,
        code=m.code,
        kind=m.kind,
        dim=m.dim,
        defaults=m.defaults,
        upstream_name=m.upstream_name,
        capabilities=m.capabilities,
        enabled=m.enabled,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


router = APIRouter(prefix="/v1/admin/models", tags=["admin:models"])


@router.get("", response_model=Result[list[ModelItem]])
async def list_models(
    kind: str | None = Query(default=None, pattern="^(chat|embedding|rerank|image|video)$"),
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
    audit: AuditContext = Depends(get_audit_context),
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
        upstream_name=req.upstream_name,
        capabilities=req.capabilities,
        enabled=True,
    )
    session.add(m)
    await session.flush()
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="model.create",
        resource_type="model",
        resource_id=m.id,
        after={"code": m.code, "kind": m.kind, "provider_id": m.provider_id},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    await session.commit()
    # commit 后 updated_at（server onupdate）会过期；在 async 上下文 refresh 后再读，
    # 避免 _to_item 同步访问触发懒加载 → MissingGreenlet。reload 放到取完值之后。
    await session.refresh(m)
    item = _to_item(m, provider.code)
    await reload_llm_cache()
    await reload_embedding_cache()
    await reload_rerank_cache()
    return Result.ok(item)


@router.post("/{model_id}/update", response_model=Result[ModelItem])
async def update_model(
    model_id: int,
    req: UpdateModelRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
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
    if req.provider_id is not None and req.provider_id != m.provider_id:
        prov = (
            await session.execute(
                select(Provider).where(
                    Provider.id == req.provider_id, Provider.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        if prov is None:
            raise ValidationError(message=f"provider 不存在: {req.provider_id}")
        m.provider_id = req.provider_id
    if req.code is not None and req.code != m.code:
        dup = (
            await session.execute(
                select(LLMModel).where(
                    LLMModel.provider_id == m.provider_id,
                    LLMModel.code == req.code,
                    LLMModel.id != m.id,
                    LLMModel.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            raise ValidationError(message=f"同 provider 已有同 code 的 model: {req.code}")
        m.code = req.code
    if req.dim is not None:
        m.dim = req.dim
    if req.defaults is not None:
        m.defaults = req.defaults
    if req.enabled is not None:
        m.enabled = req.enabled
    if req.upstream_name is not None:
        m.upstream_name = req.upstream_name
    if req.capabilities is not None:
        m.capabilities = req.capabilities
    await session.flush()
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="model.update",
        resource_type="model",
        resource_id=m.id,
        after={"code": m.code, "enabled": m.enabled, "dim": m.dim},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    await session.commit()
    # commit 后 updated_at（server onupdate）会过期；在 async 上下文 refresh 后再读，
    # 避免 _to_item 同步访问触发懒加载 → MissingGreenlet。reload 放到取完值之后。
    await session.refresh(m)
    item = _to_item(m)
    await reload_llm_cache()
    await reload_embedding_cache()
    await reload_rerank_cache()
    return Result.ok(item)


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

    # 与工厂同口径解析有效上游（newapi 模式走网关）：保证「测试」== 实际调用
    base_url, api_key, upstream_model = await resolve_upstream(session, m, p)
    if not base_url:
        return Result.ok(
            TestModelResult(ok=False, latency_ms=0, sample="", detail="provider.base_url 未配置")
        )

    start = time.monotonic()
    try:
        if m.kind == "chat":
            defaults = m.defaults or {}
            client = BaseLLM(
                model=upstream_model,
                api_key=api_key,
                api_base=base_url,
                temperature=defaults.get("temperature", 0.7),
                max_tokens=5,
            )
            resp = await client.ainvoke("ping")
            content = getattr(resp, "content", "") or ""
            sample = str(content)[:60] if content else "(空回复)"
        elif m.kind == "embedding":
            dim = m.dim or 1536
            client = OpenAICompatEmbedding(
                base_url=base_url,
                api_key=api_key,
                model=upstream_model,
                model_code=m.code,
                dim=int(dim),
            )
            vectors = await client.embed(["hello"])
            sample = f"vector[dim={len(vectors[0])}]"
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
            if results:
                top = max(results, key=lambda r: r.score)
                sample = f"命中 #{top.index} 分数 {round(top.score, 4)}"
            else:
                sample = "(空结果)"
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
    # image/video 模型：生成面板的可调参数（size / n / negative_prompt / seed …）
    params: dict | None = None
    # video(i2v) 模型：首帧/参考图片 url（来自附件上传）
    input_images: list[str] | None = None


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
    return sse_response(
        test_service.stream_test(
            session,
            model_id=model_id,
            prompt=req.prompt if req else None,
            params=req.params if req else None,
            input_images=req.input_images if req else None,
        ),
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
    await reload_embedding_cache()
    await reload_rerank_cache()
    return Result.ok(None)
