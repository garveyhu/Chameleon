"""Playground 调试服务：直调 LLM 流式 + 可选 KB context prepend

不写 call_logs（admin 调试用），不走 conversations。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.core.api.sse_events import (
    UsagePayload,
    event_delta,
    event_end,
)
from chameleon.core.components.llms.factory import resolve_llm
from chameleon.core.models import KnowledgeBase, LLMModel
from chameleon.system.kbs.document_service import search_chunks

PLAYGROUND_TOP_K = 3
PLAYGROUND_CTX_HEADER = "以下是参考资料，请基于这些资料作答（无关时可忽略）：\n"


async def get_model_name(session: AsyncSession, model_id: int) -> str:
    row = (
        await session.execute(select(LLMModel).where(LLMModel.id == model_id))
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(ResultCode.Fail, message=f"model 不存在: {model_id}")
    return row.code


async def build_kb_context(
    session: AsyncSession, *, query: str, kb_ids: list[int]
) -> str:
    """从所选 KB 检索 top chunks，拼成 system 段前缀文本。"""
    if not kb_ids:
        return ""
    pieces: list[str] = []
    for kb_id in kb_ids:
        # 校验 kb 存在 + 取 default mode
        kb = (
            await session.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == kb_id,
                    KnowledgeBase.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if kb is None:
            continue
        try:
            hits = await search_chunks(
                session,
                kb_id=kb.id,
                query=query,
                top_k=PLAYGROUND_TOP_K,
                mode=kb.recall_mode,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "playground kb retrieval failed | kb={} | query_len={}",
                kb_id,
                len(query),
            )
            continue
        for h in hits:
            pieces.append(
                f"[{kb.name}#{h['doc_id']}#{h['seq']}] {h['content']}"
            )
    if not pieces:
        return ""
    return PLAYGROUND_CTX_HEADER + "\n\n".join(pieces) + "\n\n"


def build_messages(
    *,
    system_prompt: str | None,
    kb_context: str,
    messages: list[dict],
) -> list:
    """把 system + (kb_context 拼到 system 前缀) + 历史 message → LangChain messages"""
    out = []
    sys_parts: list[str] = []
    if kb_context:
        sys_parts.append(kb_context)
    if system_prompt:
        sys_parts.append(system_prompt)
    if sys_parts:
        out.append(SystemMessage(content="\n\n".join(sys_parts)))

    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
        elif role == "system":
            # 已合并在 system_prompt；忽略
            continue
        else:
            raise ValidationError(message=f"unsupported message role: {role}")
    if not out or not isinstance(out[-1], HumanMessage):
        raise ValidationError(message="messages 末条必须是 user")
    return out


async def invoke_stream(
    session: AsyncSession,
    *,
    model_id: int | None,
    model_name: str | None,
    system_prompt: str | None,
    temperature: float,
    top_p: float | None,
    max_tokens: int | None,
    messages: list[dict],
    kb_ids: list[int],
) -> AsyncIterator[dict]:
    """完整 playground 调用编排：解析 model → 拉 KB context → 拼 message → 流式调用。

    抛 ValidationError / BusinessError 都视为业务错误，由上层 sse_response 兜底成 error chunk。
    """
    resolved_model = model_name
    if not resolved_model:
        if model_id is None:
            raise ValidationError(message="必须提供 model_id 或 model_name")
        resolved_model = await get_model_name(session, model_id)

    last_user = next((m for m in reversed(messages) if m.get("role") == "user"), None)
    if last_user is None:
        raise ValidationError(message="messages 中至少有一条 user")

    kb_context = await build_kb_context(
        session, query=last_user.get("content", ""), kb_ids=kb_ids
    )
    lc_messages = build_messages(
        system_prompt=system_prompt,
        kb_context=kb_context,
        messages=messages,
    )

    async for chunk in _stream_llm(
        session,
        model_name=resolved_model,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        messages=lc_messages,
    ):
        yield chunk


async def _stream_llm(
    session: AsyncSession,
    *,
    model_name: str,
    temperature: float,
    top_p: float | None,
    max_tokens: int | None,
    messages: list,
) -> AsyncIterator[dict]:
    """直接走 LLM .astream，逐 token yield {"delta": str}；末尾 {"end": True, "usage": ...}。"""
    # #30：per-request 经 channel 路由（含 C7 key 轮转）解析 LLM；无 channel 回退 cache
    llm = await resolve_llm(
        model_name, session=session, temperature=temperature, max_tokens=max_tokens
    )
    # 覆盖运行时参数（不污染 cache）
    bound_kwargs: dict = {"temperature": temperature}
    if top_p is not None:
        bound_kwargs["top_p"] = top_p
    if max_tokens is not None:
        bound_kwargs["max_tokens"] = max_tokens
    bound = llm.bind(**bound_kwargs)

    usage: UsagePayload | None = None
    async for chunk in bound.astream(messages):
        text = getattr(chunk, "content", None)
        if text:
            yield event_delta(text)
        # langchain_openai 流末带 usage_metadata
        u = getattr(chunk, "usage_metadata", None)
        if u:
            usage = UsagePayload.from_dict(u)
    yield event_end(usage=usage)
