"""Playground 路由（/v1/admin/playground）

POST /v1/admin/playground/invoke 走 SSE 流，不写 call_logs / conversations。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import ValidationError
from chameleon.core.infra.db import get_session
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.playground import service


class PlaygroundMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


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
    """SSE 流式调用，event-stream content-type；data: {"delta":"..."}\\n\\n"""
    if not req.model_id and not req.model_name:
        raise ValidationError(message="必须提供 model_id 或 model_name")

    model_name = req.model_name
    if not model_name:
        model_name = await service.get_model_name(session, req.model_id)

    # 取最近一条 user 文本做 KB 检索 query
    last_user = next(
        (m for m in reversed(req.messages) if m.role == "user"), None
    )
    if last_user is None:
        raise ValidationError(message="messages 中至少有一条 user")
    kb_context = await service.build_kb_context(
        session, query=last_user.content, kb_ids=req.kb_ids or []
    )

    messages = service.build_messages(
        system_prompt=req.system_prompt,
        kb_context=kb_context,
        messages=[m.model_dump() for m in req.messages],
    )

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            async for chunk in service.stream_invoke(
                model_name=model_name,
                temperature=req.temperature,
                top_p=req.top_p,
                max_tokens=req.max_tokens,
                messages=messages,
            ):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode(
                    "utf-8"
                )
        except Exception as e:  # noqa: BLE001
            logger.exception("playground stream failed")
            err = json.dumps(
                {"error": {"type": type(e).__name__, "message": str(e)[:300]}},
                ensure_ascii=False,
            )
            yield f"data: {err}\n\n".encode("utf-8")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx 不缓冲
        },
    )
