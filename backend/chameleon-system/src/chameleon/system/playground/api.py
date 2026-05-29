"""Playground 路由（/v1/admin/playground）

POST /v1/admin/playground/invoke 走 SSE 流，绑定 owner key 溯源（channel='playground'）
落 ChatSession + messages + call_log 根行，与嵌入式同构。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import ValidationError
from chameleon.core.api.sse import sse_response
from chameleon.core.infra.db import get_session
from chameleon.system.auth.dependencies import CurrentUser, require_permission
from chameleon.system.playground import service


class PlaygroundMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    # P19.4 PR #42：multimodal —— content 既可纯字符串，也可 ContentBlock 列表
    # 形态：[{"type":"text","text":"..."}, {"type":"image_url","image_url":{"url":"..."}}]
    content: str | list[dict]


class PlaygroundInvokeRequest(BaseModel):
    # 溯源：必须绑定一个 owner key（系统理念——模型随便用，但流量必须挂在 key 上）
    api_key_id: int | None = None
    # 会话续接：首条不传，service 建会话后经 meta 透出 session_id，后续轮带上
    session_id: str | None = None
    # 应用关联：本会话基于哪个应用预填配置（仅记录溯源，运行仍 model-direct）
    bound_agent_key: str | None = None
    model_id: int | None = None
    model_name: str | None = None
    system_prompt: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)
    messages: list[PlaygroundMessage]
    kb_ids: list[int] | None = None
    # 是否把本轮配置写入会话快照；transient 调用（如翻译临时指令）传 false 不污染
    persist_config: bool = True


router = APIRouter(prefix="/v1/admin/playground", tags=["admin:playground"])


@router.post("/invoke")
async def invoke(
    req: PlaygroundInvokeRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(require_permission("playground:invoke")),
):
    """SSE 流式调用：业务编排全部在 service.invoke_stream，API 层只做请求/响应桥接。"""
    if not req.model_id and not req.model_name:
        raise ValidationError(message="必须提供 model_id 或 model_name")

    return sse_response(
        service.invoke_stream(
            session,
            api_key_id=req.api_key_id,
            session_id=req.session_id,
            bound_agent_key=req.bound_agent_key,
            # 操作者即终端用户：登录 admin 的 id 落 end_user_id（溯源「谁跑的」）
            operator_user_id=user.id,
            model_id=req.model_id,
            model_name=req.model_name,
            system_prompt=req.system_prompt,
            temperature=req.temperature,
            top_p=req.top_p,
            max_tokens=req.max_tokens,
            messages=[m.model_dump() for m in req.messages],
            kb_ids=req.kb_ids or [],
            persist_config=req.persist_config,
        ),
        log_label="playground:invoke",
    )
