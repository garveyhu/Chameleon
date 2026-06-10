"""StreamEvent → 站内 SSE chunk 的统一转换器（翻译层收口）

背景：playground / embed 各自手写「挑事件」循环把 provider 的 StreamEvent
翻成 B 格式 chunk（匿名 data 行，按顶层 key 判型），逻辑重复且持续漂移——
新增事件类型（pending / usage / guardrail 字段）需要 N 处同步，漏一处就是
一个渠道的静默丢事件（审计根因 #1）。

本模块把「事件 → chunk」的映射收成一个纯函数，渠道循环只保留各自的
渠道逻辑（聚合、落库、end 组装）。设计对标 Vercel AI SDK v5 UI Message
Stream 的单一翻译器思路；线格式维持现状（与 widget / 文档已对齐）。

映射表（与 core/api/sse_events 的 chunk 词汇一致）：

| StreamEvent                      | chunk                                      |
|----------------------------------|--------------------------------------------|
| delta {text}                     | {"delta": text}                            |
| citation {...}                   | {"citation": {...}}（show_citations 门控） |
| step name=human_input_pending    | {"pending": {prompt, call_index, run_id}}  |
| step 其他                        | 丢弃（过程步暂不透传站内渠道）             |
| metadata {usage}                 | 暂存进 state.usage（end 时由调用方取用）   |
| metadata 其他（media 等）        | 丢弃（媒体走 delta markdown，作者侧约定）  |
| tool_call / tool_result          | 丢弃（同 step；接入 thought 渲染时此处开闸）|
| error {...}                      | {"error": {type, message, code?, guardrail?}}|
| done                             | 丢弃（B 格式终态是 end，由调用方组装）     |

约定：error 是终态——调用方收到含 "error" 的 chunk 后应停止消费并
**不再发 end**（契约见 core/api/sse_events 模块注释）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chameleon.core.runtime_types import StreamEvent, StreamEventType

__all__ = ["StreamTranslateState", "translate_event"]


@dataclass
class StreamTranslateState:
    """跨事件累积状态。

    usage：provider 流末经 metadata 上报（OpenAI 命名），end 组装时由调用方
    取 `usage_sse()`（LangFuse 命名 input/output_tokens——SSE 层统一约定）。
    """

    usage: dict[str, Any] | None = None
    saw_error: bool = False
    saw_pending: bool = False
    _extras: dict[str, Any] = field(default_factory=dict)

    def usage_sse(self) -> dict[str, int] | None:
        """OpenAI 命名（prompt/completion）→ SSE 层命名（input/output）。"""
        u = self.usage
        if not u or not u.get("total_tokens"):
            return None
        return {
            "input_tokens": u.get("prompt_tokens") or u.get("input_tokens") or 0,
            "output_tokens": u.get("completion_tokens")
            or u.get("output_tokens")
            or 0,
            "total_tokens": u.get("total_tokens") or 0,
        }


def translate_event(
    ev: StreamEvent,
    state: StreamTranslateState,
    *,
    show_citations: bool = True,
) -> list[dict[str, Any]]:
    """单个 provider StreamEvent → 0..n 个站内 SSE chunk（B 格式）。

    纯函数（除 state 累积），不做 IO；渠道循环负责 yield 与渠道逻辑。
    """
    if ev.type == StreamEventType.delta:
        text = ev.data.get("text", "")
        return [{"delta": text}] if text else []

    if ev.type == StreamEventType.citation:
        return [{"citation": ev.data}] if show_citations else []

    if ev.type == StreamEventType.step:
        if ev.data.get("name") == "human_input_pending":
            state.saw_pending = True
            return [
                {
                    "pending": {
                        "prompt": ev.data.get("prompt", ""),
                        "call_index": ev.data.get("call_index"),
                        "run_id": ev.data.get("run_id"),
                    }
                }
            ]
        return []

    if ev.type == StreamEventType.metadata:
        u = ev.data.get("usage")
        if isinstance(u, dict):
            state.usage = u
        return []

    if ev.type == StreamEventType.error:
        state.saw_error = True
        err: dict[str, Any] = {
            "type": ev.data.get("type", "ProviderError"),
            "message": ev.data.get("message", "provider stream error"),
        }
        if ev.data.get("code") is not None:
            err["code"] = ev.data["code"]
        # guardrail 拦截等结构化字段透传，前端可差异化展示
        if ev.data.get("guardrail"):
            err["guardrail"] = ev.data["guardrail"]
        return [{"error": err}]

    # tool_call / tool_result / done：站内渠道暂不透传（接 thought 渲染时开闸）
    return []
