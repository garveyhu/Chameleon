"""内部 LLM 调用统一执行层。

收口系统各域散落的 `get_llm + ainvoke + 容错 + set_trace_context` 样板（见
docs/plans/2026-06-07-internal-llm-aikit.md §3）。职责严格限定在「执行截面」：
拿 client → 调用 → 重试 / 容错降级 → 在正确 channel 的 trace scope 内执行。
**不承载任何业务 prompt 语义**——业务 prompt 由通用任务（tasks/）或域内纯函数提供。

trace 复用红线：若调用时已处于某个 `TraceContext` scope（如评测 runner 已开
channel='eval'），**沿用外层归属、绝不覆盖**；只有完全无 scope 的裸调用才用传入的
channel/app_id/session_id 自开一个 scope 补记账。既不破坏现有 eval 计费归属，又给
散调用补上可观测。
"""

from __future__ import annotations

import uuid
from typing import Any, AsyncIterator

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from loguru import logger

from chameleon.core.observe.context import (
    TraceContext,
    current_trace_context,
    open_trace_scope,
)
from chameleon.integrations.llms.factory import LLMFactory

DEFAULT_CHANNEL = "internal"

# 一段 prompt：纯文本，或已构造好的 LangChain 消息列表
Prompt = str | list[BaseMessage]


def _to_messages(prompt: Prompt, system: str | None) -> list[BaseMessage]:
    """把 str / 消息列表归一为 LangChain 消息列表（str 时可附加 system）。"""
    if isinstance(prompt, str):
        msgs: list[BaseMessage] = []
        if system:
            msgs.append(SystemMessage(content=system))
        msgs.append(HumanMessage(content=prompt))
        return msgs
    return prompt


def _content_text(chunk: Any) -> str:
    """从 AIMessage / chunk 取纯文本（兼容多模态分段 list[str|dict]）。"""
    content = getattr(chunk, "content", chunk)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for seg in content:
            if isinstance(seg, str):
                parts.append(seg)
            elif isinstance(seg, dict):
                t = seg.get("text")
                if isinstance(t, str):
                    parts.append(t)
        return "".join(parts)
    return str(content)


def _new_scope_ctx(
    channel: str, app_id: str | None, session_id: str | None
) -> TraceContext:
    return TraceContext(
        request_id=uuid.uuid4().hex,
        channel=channel,
        app_id=app_id,
        session_id=session_id,
    )


class LLMRunner:
    """内部 LLM 调用的统一执行器（无状态，全静态方法）。"""

    @staticmethod
    async def run_text(
        prompt: Prompt,
        *,
        model: str | None = None,
        channel: str = DEFAULT_CHANNEL,
        app_id: str | None = None,
        session_id: str | None = None,
        system: str | None = None,
        retries: int = 1,
        fallback: str | None = None,
    ) -> str:
        """一次性调用取完整文本。

        Args:
            prompt: 用户 prompt 文本，或已构造的消息列表。
            model: 模型 code；None 走系统默认模型。
            channel: 无外层 trace scope 时自开的 channel；已有 scope 则忽略。
            app_id: 自开 scope 的归属 app（如评测 EVAL_APP_ID）；已有 scope 忽略。
            session_id: 自开 scope 的会话标识（trace 分组）；已有 scope 忽略。
            system: prompt 为 str 时附加的 system 提示。
            retries: 失败重试次数（总尝试 = retries + 1）。
            fallback: 全部失败时返回的兜底文本；None 则向上抛。

        Returns:
            LLM 输出文本。

        Raises:
            Exception: retries 用尽且未给 fallback 时，抛最后一次异常。
        """
        messages = _to_messages(prompt, system)
        if current_trace_context() is not None:
            return await LLMRunner._invoke_with_retry(
                model, messages, retries, fallback
            )
        async with open_trace_scope(_new_scope_ctx(channel, app_id, session_id)):
            return await LLMRunner._invoke_with_retry(
                model, messages, retries, fallback
            )

    @staticmethod
    async def run_stream(
        prompt: Prompt,
        *,
        model: str | None = None,
        channel: str = DEFAULT_CHANNEL,
        app_id: str | None = None,
        session_id: str | None = None,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        """流式调用，逐增量 yield 文本（无重试——流式中途失败由调用方处理）。"""
        messages = _to_messages(prompt, system)
        if current_trace_context() is not None:
            async for delta in LLMRunner._astream(model, messages):
                yield delta
            return
        async with open_trace_scope(_new_scope_ctx(channel, app_id, session_id)):
            async for delta in LLMRunner._astream(model, messages):
                yield delta

    # ── 内部实现 ──────────────────────────────────────────────

    @staticmethod
    async def _invoke_with_retry(
        model: str | None,
        messages: list[BaseMessage],
        retries: int,
        fallback: str | None,
    ) -> str:
        client = LLMFactory.create(model)
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                ai = await client.ainvoke(messages)
                return _content_text(ai)
            except Exception as exc:  # noqa: BLE001 —— 统一容错边界
                last_exc = exc
                logger.warning(
                    "aikit LLM 调用失败 model={} attempt={}/{}: {}",
                    model or "<default>",
                    attempt + 1,
                    retries + 1,
                    exc,
                )
        if fallback is not None:
            logger.warning("aikit LLM 调用全失败，返回 fallback")
            return fallback
        assert last_exc is not None
        raise last_exc

    @staticmethod
    async def _astream(
        model: str | None, messages: list[BaseMessage]
    ) -> AsyncIterator[str]:
        client = LLMFactory.create(model)
        async for chunk in client.astream(messages):
            text = _content_text(chunk)
            if text:
                yield text


class LLMTask:
    """通用内部 AI 任务基类（备未来跨域复用的通用能力）。

    子类声明 `key` / `channel`，实现 `build_prompt()` 与 `parse()`；`run()` 把两者经
    `LLMRunner` 串起来。仅用于**无业务语义的通用能力**；带强域语义的任务把 prompt/parse
    留在域内、只复用 `LLMRunner`，不继承本类。
    """

    key: str
    channel: str = DEFAULT_CHANNEL

    def build_prompt(self, **inputs: Any) -> Prompt:
        raise NotImplementedError

    def parse(self, raw: str) -> Any:
        return raw

    async def run(
        self, *, model: str | None = None, retries: int = 1, **inputs: Any
    ) -> Any:
        raw = await LLMRunner.run_text(
            self.build_prompt(**inputs),
            model=model,
            channel=self.channel,
            retries=retries,
        )
        return self.parse(raw)
