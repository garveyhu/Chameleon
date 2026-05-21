"""EchoChatModel —— 假装是 LLM，按字符 stream 回输入文本

存在的意义：让 echo agent 能产 on_chat_model_stream 事件，
langgraph_bridge 的 translate 已能识别为 delta。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


class EchoChatModel(BaseChatModel):
    """每个字符产一个 AIMessageChunk。"""

    @property
    def _llm_type(self) -> str:
        return "echo"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        text = _echo_text(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        text = _echo_text(messages)
        for ch in _by_chunks(text):
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=ch))
            if run_manager:
                run_manager.on_llm_new_token(ch, chunk=chunk)
            yield chunk

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        text = _echo_text(messages)
        for ch in _by_chunks(text):
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=ch))
            if run_manager:
                await run_manager.on_llm_new_token(ch, chunk=chunk)
            yield chunk


def _echo_text(messages: list[BaseMessage]) -> str:
    """取最后一条 user 消息，echo: 前缀"""
    last_user = next(
        (m for m in reversed(messages) if isinstance(m, HumanMessage)),
        None,
    )
    if last_user is None:
        return "echo: (no input)"
    content = last_user.content
    if isinstance(content, list):
        # 多模态时拼 text 部分
        parts = [p.get("text", "") for p in content if isinstance(p, dict)]
        content = "".join(parts)
    return f"echo: {content}"


def _by_chunks(text: str, size: int = 2) -> list[str]:
    """按 size 字符切片，模拟 token 流"""
    return [text[i : i + size] for i in range(0, len(text), size)]
