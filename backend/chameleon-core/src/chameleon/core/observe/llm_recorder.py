"""GenerationRecorder —— LangChain BaseLLM 异步回调，每次模型调用落一条 call_log

S5 切面收口的核心：
- 探针挂在 BaseLLM 对象上（工厂注入时 callbacks=[GenerationRecorder(model_code)]）
- 归属靠 ContextVar：从 TraceContext 拿 app_id / api_key_id / end_user_id /
  channel / agent_key / session_id；从 current_observation_id() 拿 parent_id
- 凡是经过 LLMFactory 拿到的实例，调 .ainvoke()/.astream() 都会触发回调；
  绕过 AgentRun / 裸调 llm() 都被捕捉

无 TraceContext（KB 摄入等裸路径）→ 兜底落 channel='internal' / app_id='kb-ingest'
之类，永远不丢账。

实现要点：
- 使用 LangChain run_id 作为每次调用的唯一键（在 on_*_start 缓存 start_ms +
  prompts snapshot，on_llm_end/error 取出来计算 duration + 写库）
- 写库用独立 AsyncSessionLocal（langchain 回调上下文里无现成 session）
- I/O 快照截断（input ≤ 2KB，output ≤ 4KB，与现有 root call_log payload 对齐）
- 失败兜底：on_llm_error 也落一条 failed generation，不静默
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from loguru import logger

from chameleon.core.observe.context import (
    ObservationType,
    current_observation_id,
    current_trace_context,
)

# I/O 快照截断阈值（与现有 root call_log payload 对齐）
_INPUT_TRUNCATE = 2000
_OUTPUT_TRUNCATE = 4000
# 结构化消息单条 content 截断（保留 LangChain 原生 messages 形态，而非拍平成字符串）
_MSG_CONTENT_MAX = 8000
# BaseMessage.type → 标准角色（human→user / ai→assistant），前端按角色渲染
_ROLE_NORM = {
    "system": "system",
    "human": "user",
    "ai": "assistant",
    "tool": "tool",
    "function": "tool",
    "chat": "assistant",
}


def _content_of(msg: Any) -> str:
    """从 LangChain BaseMessage 取纯文本 content（兼容 list[ContentBlock]）"""
    content = getattr(msg, "content", msg)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for b in content:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                text = b.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content) if content is not None else ""


def _usage_from_response(response: Any) -> tuple[int | None, int | None, int | None]:
    """从 LLMResult 取 token 用量（兼容流式 usage_metadata + 非流式 llm_output）"""
    prompt = completion = total = None

    # 路径一：流式（BaseLLM 已设 stream_usage=True）—— AIMessage.usage_metadata
    try:
        gen = response.generations[0][0]
        msg = getattr(gen, "message", None)
        um = getattr(msg, "usage_metadata", None) if msg is not None else None
        if isinstance(um, dict):
            prompt = um.get("input_tokens")
            completion = um.get("output_tokens")
            total = um.get("total_tokens")
            if total is None and (prompt is not None or completion is not None):
                total = (prompt or 0) + (completion or 0)
            if any(v is not None for v in (prompt, completion, total)):
                return prompt, completion, total
    except (AttributeError, IndexError, TypeError):
        pass

    # 路径二：非流式 —— llm_output.token_usage
    try:
        tu = (response.llm_output or {}).get("token_usage") or {}
        prompt = tu.get("prompt_tokens")
        completion = tu.get("completion_tokens")
        total = tu.get("total_tokens")
    except (AttributeError, TypeError):
        pass

    return prompt, completion, total


def _output_text(response: Any) -> str:
    """从 LLMResult 取 assistant 输出（首个 generation 的 message.content）"""
    try:
        gen = response.generations[0][0]
        msg = getattr(gen, "message", None)
        if msg is not None:
            return _content_of(msg)
        return getattr(gen, "text", "") or ""
    except (AttributeError, IndexError):
        return ""


class GenerationRecorder(AsyncCallbackHandler):
    """模型调用 generation 行记录器（一次 .ainvoke()/.astream() 落一行）"""

    raise_error: bool = False  # langchain 默认即可：回调内部错误不上抛
    run_inline: bool = True  # 在调用方协程内同步跑（保留 ContextVar 可见）

    def __init__(self, model_code: str) -> None:
        self.model_code = model_code
        # 用 run_id 关联 start/end；每个 run 不会跨多个 callback 实例
        self._inflight: dict[str, dict[str, Any]] = {}

    # ── start ──────────────────────────────────────────────

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id,
        parent_run_id=None,
        **kwargs: Any,
    ) -> None:
        del serialized, parent_run_id, kwargs
        self._inflight[str(run_id)] = {
            "start_ms": time.perf_counter(),
            "messages": self._snapshot_messages(messages),
        }

    async def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id,
        parent_run_id=None,
        **kwargs: Any,
    ) -> None:
        del serialized, parent_run_id, kwargs
        joined = "\n".join(prompts or [])
        # 纯补全（无角色）→ 包成单条 user 消息，保持 messages 形态统一
        msgs = [{"role": "user", "content": joined[:_MSG_CONTENT_MAX]}] if joined else []
        self._inflight[str(run_id)] = {
            "start_ms": time.perf_counter(),
            "messages": msgs,
        }

    # ── end / error ───────────────────────────────────────

    async def on_llm_end(self, response: Any, *, run_id, **kwargs: Any) -> None:
        del kwargs
        meta = self._inflight.pop(str(run_id), None) or {}
        start_ms = meta.get("start_ms")
        duration_ms = (
            int((time.perf_counter() - start_ms) * 1000) if start_ms else 0
        )
        prompt_tokens, completion_tokens, total_tokens = _usage_from_response(response)
        output_text = _output_text(response)

        await self._write(
            success=True,
            code=0,
            error_message=None,
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            messages=meta.get("messages"),
            output_preview=output_text[:_OUTPUT_TRUNCATE] if output_text else None,
        )

    async def on_llm_error(self, error: BaseException, *, run_id, **kwargs: Any) -> None:
        del kwargs
        meta = self._inflight.pop(str(run_id), None) or {}
        start_ms = meta.get("start_ms")
        duration_ms = (
            int((time.perf_counter() - start_ms) * 1000) if start_ms else 0
        )
        await self._write(
            success=False,
            code=500,
            error_message=f"{type(error).__name__}: {str(error)[:300]}",
            duration_ms=duration_ms,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            messages=meta.get("messages"),
            output_preview=None,
        )

    # ── helpers ───────────────────────────────────────────

    @staticmethod
    def _snapshot_messages(messages: list[list[Any]]) -> list[dict]:
        """把 list[list[BaseMessage]] 转成结构化 [{role, content}]（保留 LangChain 形态）。

        不再拍平成 "[role] ..." 字符串——结构化存储让前端按角色/历史/本轮分组渲染，
        且可无损导出。content 取纯文本（多模态 ContentBlock 由 _content_of 抽文本）。
        """
        first_group = messages[0] if messages else []
        out: list[dict] = []
        for m in first_group:
            raw = (getattr(m, "type", None) or m.__class__.__name__).lower()
            out.append(
                {
                    "role": _ROLE_NORM.get(raw, raw),
                    "content": _content_of(m)[:_MSG_CONTENT_MAX],
                }
            )
        return out

    async def _write(
        self,
        *,
        success: bool,
        code: int,
        error_message: str | None,
        duration_ms: int,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
        messages: list[dict] | None,
        output_preview: str | None,
    ) -> None:
        """落一条 generation call_log；归属字段从 TraceContext 拿，无 scope 兜底"""
        # 延迟 import 避免循环依赖（infra/db 反过来依赖 models → observe）
        from chameleon.core.observe.sink import record_observation
        from chameleon.data.infra.db import AsyncSessionLocal

        tc = current_trace_context()
        parent_id = current_observation_id() or (tc.request_id if tc else None)

        # 归属冗余字段：有 TraceContext 取之，没有兜底
        app_id = tc.app_id if tc else "internal"
        agent_key = tc.agent_key if tc else "internal"
        session_id = tc.session_id if tc else None
        channel = tc.channel if tc else "internal"
        api_key_id = tc.api_key_id if tc else None
        end_user_id = tc.end_user_id if tc else None
        user_id = tc.user_id if tc else None

        gen_request_id = uuid.uuid4().hex

        try:
            async with AsyncSessionLocal() as session:
                await record_observation(
                    session,
                    request_id=gen_request_id,
                    app_id=app_id or "internal",
                    agent_key=agent_key or "internal",
                    session_id=session_id,
                    stream=False,  # 由调用方区分；流式也是一次 generation 行
                    success=success,
                    code=code,
                    error_message=error_message,
                    duration_ms=duration_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    spans=None,
                    request_payload=({"messages": messages} if messages else None),
                    response_payload=(
                        {"output": output_preview} if output_preview else None
                    ),
                    parent_id=parent_id,
                    observation_type=ObservationType.GENERATION.value,
                    model_code=self.model_code,
                    user_id=user_id,
                    channel=channel,
                    api_key_id=api_key_id,
                    end_user_id=end_user_id,
                )
                await session.commit()
        except Exception:  # noqa: BLE001
            logger.exception(
                "generation record failed | model={} | run_request_id={}",
                self.model_code,
                gen_request_id,
            )
