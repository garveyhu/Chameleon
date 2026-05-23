"""Playground 路由（/v1/admin/playground）

POST /v1/admin/playground/invoke 走 SSE 流，不写 call_logs / conversations。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import ValidationError
from chameleon.core.api.sse import sse_response
from chameleon.core.infra.db import get_session
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.playground import service


class PlaygroundMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    # P19.4 PR #42：multimodal —— content 既可纯字符串，也可 ContentBlock 列表
    # 形态：[{"type":"text","text":"..."}, {"type":"image_url","image_url":{"url":"..."}}]
    content: str | list[dict]


class PlaygroundInvokeRequest(BaseModel):
    model_id: int | None = None
    model_name: str | None = None
    system_prompt: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)
    messages: list[PlaygroundMessage]
    kb_ids: list[int] | None = None


router = APIRouter(prefix="/v1/admin/playground", tags=["admin:playground"])


@router.post("/invoke")
async def invoke(
    req: PlaygroundInvokeRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("playground:invoke")),
):
    """SSE 流式调用：业务编排全部在 service.invoke_stream，API 层只做请求/响应桥接。"""
    if not req.model_id and not req.model_name:
        raise ValidationError(message="必须提供 model_id 或 model_name")

    return sse_response(
        service.invoke_stream(
            session,
            model_id=req.model_id,
            model_name=req.model_name,
            system_prompt=req.system_prompt,
            temperature=req.temperature,
            top_p=req.top_p,
            max_tokens=req.max_tokens,
            messages=[m.model_dump() for m in req.messages],
            kb_ids=req.kb_ids or [],
        ),
        log_label="playground:invoke",
    )
