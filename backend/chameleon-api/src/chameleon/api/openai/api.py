"""OpenAI 兼容网关（P5-4）：POST /v1/chat/completions

把 OpenAI chat.completions 请求适配到内部 agent invoke（model = agent_key），
让任意 OpenAI 客户端/SDK 直接调用本平台的智能体（含 graph 编排出来的）。
鉴权同 /v1/invoke：api_key → App。复用 service.invoke / stream_invoke。
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.agent import service
from chameleon.api.agent.schemas import InvokeRequest, MessageInput
from chameleon.api.openai.schemas import OAChatRequest
from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.data.infra.auth import CurrentApp, current_app
from chameleon.data.infra.db import get_session

router = APIRouter(prefix="/v1", tags=["openai-compat"])

# OpenAI 新版把 system 改叫 developer —— 映射回内部 system；其余未知 role 报 400
_ROLE_MAP = {"developer": "system"}
_KNOWN_ROLES = ("user", "assistant", "system", "tool")


def _to_invoke_request(req: OAChatRequest) -> InvokeRequest:
    messages: list[MessageInput] = []
    for m in req.messages:
        role = _ROLE_MAP.get(m.role, m.role)
        if role not in _KNOWN_ROLES:
            raise BusinessError(
                ResultCode.ValidationError,
                message=f"不支持的 message role: {m.role}",
            )
        messages.append(MessageInput(role=role, content=m.content))
    return InvokeRequest(
        input=messages,
        session_id=req.session_id,
        user=req.user,
        stream=req.stream,
    )


def _err_chunk(message: str, code: int | None = None) -> str:
    """OpenAI 风格流中错误对象（error.type/code/message）"""
    err: dict = {
        "message": message,
        "type": "invalid_request_error" if code and code < 50000 else "server_error",
    }
    if code is not None:
        err["code"] = code
    return f"data: {json.dumps({'error': err}, ensure_ascii=False)}\n\n"


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
    request_id = getattr(request.state, "request_id", "req_unknown")

    ir = _to_invoke_request(req)
    cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    if req.stream:

        async def gen() -> AsyncIterator[str]:
            sent_role = False
            try:
                async for ev in service.stream_invoke(
                    req.model,
                    ir,
                    current_app=app,
                    request_id=request_id,
                    channel="openai",
                ):
                    if ev.type.value == "delta":
                        text = ev.data.get("text", "")
                        if text:
                            if not sent_role:
                                # OpenAI 标准：首 chunk delta 带 role
                                yield _chunk(
                                    cid, created, req.model,
                                    {"role": "assistant"}, None,
                                )
                                sent_role = True
                            yield _chunk(
                                cid, created, req.model, {"content": text}, None
                            )
                    elif ev.type.value == "error":
                        yield _err_chunk(
                            ev.data.get("message", "error"), ev.data.get("code")
                        )
                        yield "data: [DONE]\n\n"
                        return
                yield _chunk(cid, created, req.model, {}, "stop")
                yield "data: [DONE]\n\n"
            except Exception as e:  # noqa: BLE001
                # 首 chunk 前的准备异常（鉴权/agent 不存在）：200 头已发出，
                # 裸断流会让 OpenAI SDK 抛不可读的连接错误
                logger.exception("openai-compat stream failed")
                code = int(e.code) if isinstance(e, BusinessError) else None
                msg = e.message if isinstance(e, BusinessError) else str(e)[:300]
                yield _err_chunk(msg, code)
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    resp = await service.invoke(
        session, req.model, ir, current_app=app, request_id=request_id, channel="openai"
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
