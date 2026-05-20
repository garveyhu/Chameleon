"""agent 业务编排服务

非流路径 9 步（设计文档 S4.3 ①-⑨）：
  ① 注册表查询
  ② 会话处理（创建 or 拿已有）
  ③ 历史装载（str → 取 session；list → 客户端自管，不取）
  ④ 落库 user msg（先写防丢）
  ⑤ 装 InvokeContext
  ⑥ 调 provider.invoke
  ⑦ 落库 assistant msg
  ⑧ touch 会话（last_message_at / title / provider_conv_id）
  ⑨ 审计 call_log
"""

from __future__ import annotations

import time

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.app.modules.agent.schemas import (
    AgentItem,
    InvokeRequest,
    InvokeResponse,
)
from chameleon.app.modules.api_key import service as api_key_service
from chameleon.app.modules.conversation import service as conv_service
from chameleon.app.modules.conversation.schemas import AppendMessageDraft
from chameleon.core.auth import CurrentApp
from chameleon.core.exceptions import (
    AgentNotFoundError,
    BusinessError,
    ProviderError,
    ResultCode,
)
from chameleon.providers.base import AGENTS, PROVIDERS
from chameleon.providers.base.types import (
    AgentDef,
    InvokeContext,
)
from chameleon.providers.base.types import Message as ProviderMessage

# ── agent 列表 / 详情（注册表只读访问） ──────────────────


def list_agents() -> list[AgentItem]:
    return [
        AgentItem(
            key=a.key,
            provider=a.provider,
            description=a.description,
            version=a.version,
            tags=list(a.tags),
        )
        for a in AGENTS.values()
    ]


def get_agent(key: str) -> AgentItem:
    ad = AGENTS.get(key)
    if ad is None:
        raise AgentNotFoundError(message=f"agent 不存在: {key}")
    return AgentItem(
        key=ad.key,
        provider=ad.provider,
        description=ad.description,
        version=ad.version,
        tags=list(ad.tags),
    )


# ── 非流式 invoke 主流程 ────────────────────────────────


async def invoke(
    session: AsyncSession,
    agent_key: str,
    req: InvokeRequest,
    *,
    current_app: CurrentApp,
    request_id: str,
) -> InvokeResponse:
    start_ts = time.monotonic()

    # ① 注册表查询
    agent_def = AGENTS.get(agent_key)
    if agent_def is None:
        raise AgentNotFoundError(message=f"agent 不存在: {agent_key}")
    provider = PROVIDERS.get(agent_def.provider)
    if provider is None:
        # 理论上 init_registry 已经 fail-fast 保证，这里兜底
        raise BusinessError(
            ResultCode.RegistryError,
            message=f"provider 未注册: {agent_def.provider}",
        )

    # ② 会话处理
    conv = await _ensure_conversation(
        session,
        agent_def,
        req.session_id,
        current_app=current_app,
    )

    # ③ 历史装载（A10 裁决）
    if isinstance(req.input, str):
        history = await conv_service.load_messages(session, conv.session_id)
        current_input_text = req.input
        current_input_obj = req.input  # provider 端用 str
    else:
        # list[MessageInput]
        if not req.input:
            raise BusinessError(
                ResultCode.ValidationError, message="input 列表不能为空"
            )
        if req.input[-1].role != "user":
            raise BusinessError(
                ResultCode.ValidationError,
                message="input 列表最后一条必须是 user",
            )
        history = []  # A10：client 自管历史，service 不消费 session 历史
        current_input_text = req.input[-1].content
        current_input_obj = [
            ProviderMessage(
                role=m.role,
                content=m.content,
                name=m.name,
                tool_call_id=m.tool_call_id,
            )
            for m in req.input
        ]

    # ④ 落库 user msg（先写防丢；list 模式只落 last user，不落 client 自管历史）
    await conv_service.append(
        session,
        conv.session_id,
        AppendMessageDraft(
            role="user",
            content=current_input_text,
            provider=agent_def.provider,
        ),
    )

    # ⑤ 装 InvokeContext
    ctx = InvokeContext(
        agent_def=agent_def,
        input=current_input_obj,
        history=history,
        session_id=conv.session_id,
        provider_conv_id=conv.provider_conv_id,
        context_vars=req.context,
        options=req.options,
        app_id=current_app.app_id,
        stream=False,
        request_id=request_id,
    )

    # ⑥ 调 provider（非流式聚合）
    success = True
    code = ResultCode.Success.value
    err_msg: str | None = None
    try:
        result = await provider.invoke(ctx)
    except ProviderError as pe:
        success = False
        code = int(pe.code)
        err_msg = pe.message
        await _record_call(
            session,
            request_id=request_id,
            app_id=current_app.app_id,
            agent_key=agent_key,
            session_id=conv.session_id,
            stream=False,
            success=False,
            code=code,
            error_message=err_msg,
            duration_ms=int((time.monotonic() - start_ts) * 1000),
        )
        raise
    except Exception:
        await _record_call(
            session,
            request_id=request_id,
            app_id=current_app.app_id,
            agent_key=agent_key,
            session_id=conv.session_id,
            stream=False,
            success=False,
            code=ResultCode.InternalError.value,
            error_message="unexpected error",
            duration_ms=int((time.monotonic() - start_ts) * 1000),
        )
        raise

    # ⑦ 落库 assistant msg
    await conv_service.append(
        session,
        conv.session_id,
        AppendMessageDraft(
            role="assistant",
            content=result.answer,
            steps=[s.model_dump() for s in result.steps] or None,
            citations=[c.model_dump() for c in result.citations] or None,
            tool_calls=[tc.model_dump() for tc in result.tool_calls] or None,
            usage=result.usage.model_dump() if result.usage else None,
            provider=agent_def.provider,
        ),
    )

    # ⑧ touch（首轮自动 title）
    title = current_input_text if conv.title is None else None
    await conv_service.touch(
        session,
        conv.session_id,
        title=title,
        provider_conv_id=result.provider_conv_id,
    )

    # ⑨ 审计
    usage = result.usage
    await _record_call(
        session,
        request_id=request_id,
        app_id=current_app.app_id,
        agent_key=agent_key,
        session_id=conv.session_id,
        stream=False,
        success=success,
        code=code,
        error_message=err_msg,
        duration_ms=int((time.monotonic() - start_ts) * 1000),
        prompt_tokens=usage.prompt_tokens if usage else None,
        completion_tokens=usage.completion_tokens if usage else None,
        total_tokens=usage.total_tokens if usage else None,
    )

    return InvokeResponse(
        session_id=conv.session_id,
        request_id=request_id,
        answer=result.answer,
        steps=result.steps,
        citations=result.citations,
        tool_calls=result.tool_calls,
        usage=result.usage,
    )


# ── helpers ─────────────────────────────────────────────


async def _ensure_conversation(
    session: AsyncSession,
    agent_def: AgentDef,
    given_session_id: str | None,
    *,
    current_app: CurrentApp,
):
    """缺省 → 新建；否则取并校验权限 + agent 一致性"""
    if not given_session_id:
        return await conv_service.create(
            session,
            agent_key=agent_def.key,
            provider=agent_def.provider,
            app_id=current_app.app_id,
        )

    conv = await conv_service.get(session, given_session_id, current_app=current_app)
    # agent 一致性：同一 session 不允许切换 agent
    if conv.agent_key != agent_def.key:
        raise BusinessError(
            ResultCode.SessionIdInvalid,
            message=(
                f"session_id 已绑定 agent={conv.agent_key}，"
                f"不可用于调用 agent={agent_def.key}"
            ),
        )
    return conv


async def _record_call(session: AsyncSession, **kwargs) -> None:
    """写 call_log；失败仅 warn，不阻塞响应"""
    try:
        await api_key_service.record_call(session, **kwargs)
    except Exception:  # noqa: BLE001
        logger.warning(
            "call_log write failed | request_id={}", kwargs.get("request_id")
        )
