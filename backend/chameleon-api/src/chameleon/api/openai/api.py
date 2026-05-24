"""OpenAI 兼容网关（P5-4）：POST /v1/chat/completions

把 OpenAI chat.completions 请求适配到内部 agent invoke（model = agent_key），
让任意 OpenAI 客户端/SDK 直接调用本平台的智能体（含 graph 编排出来的）。
鉴权同 /v1/agents：api_key → App → workspace。复用 service.invoke / stream_invoke。
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.agent import service
from chameleon.api.agent.schemas import InvokeRequest, MessageInput
from chameleon.api.openai.schemas import OAChatRequest
from chameleon.core.infra.auth import CurrentApp, current_app
from chameleon.core.infra.db import get_session
from chameleon.core.observe import estimate_text_tokens

router = APIRouter(prefix="/v1", tags=["openai-compat"])


def _to_invoke_request(req: OAChatRequest) -> InvokeRequest:
    return InvokeRequest(
        input=[MessageInput(role=m.role, content=m.content) for m in req.messages],
        session_id=req.session_id,
        stream=req.stream,
    )


def _chunk(cid: str, created: int, model: str, delta: dict, finish: str | None) -> str:
    payload = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat/completions")
async def chat_completions(
    req: OAChatRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
):
    """OpenAI 兼容入口：model = agent_key。stream=true → SSE chunk + [DONE]。"""
    from chameleon.system.workspaces.quota_service import (
        assert_within_request_quota,
        pre_consume_request,
    )

    await assert_within_request_quota(session, app.workspace_id)
    request_id = getattr(request.state, "request_id", "req_unknown")
    estimated = estimate_text_tokens(" ".join(m.content for m in req.messages))
    await pre_consume_request(
        session, app.workspace_id, estimated_tokens=estimated, request_id=request_id
    )

    ir = _to_invoke_request(req)
    cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    if req.stream:

        async def gen() -> AsyncIterator[str]:
            async for ev in service.stream_invoke(
                req.model, ir, current_app=app, request_id=request_id
            ):
                if ev.type.value == "delta":
                    text = ev.data.get("text", "")
                    if text:
                        yield _chunk(cid, created, req.model, {"content": text}, None)
                elif ev.type.value == "error":
                    err = {"error": {"message": ev.data.get("message", "error")}}
                    yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
                    return
            yield _chunk(cid, created, req.model, {}, "stop")
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    resp = await service.invoke(
        session, req.model, ir, current_app=app, request_id=request_id
    )
    usage = resp.usage
    completion = {
        "id": cid,
        "object": "chat.completion",
        "created": created,
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": resp.answer},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": (usage.prompt_tokens or 0) if usage else 0,
            "completion_tokens": (usage.completion_tokens or 0) if usage else 0,
            "total_tokens": (usage.total_tokens or 0) if usage else 0,
        },
    }
    return JSONResponse(completion)
