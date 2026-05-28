"""Provider 抽象层的核心数据类型

四件套：AgentDef / InvokeContext / StreamEvent / InvokeResult
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["user", "assistant", "system", "tool"]


# ── P19.4 ContentBlock 协议 ─────────────────────────────
#
# 对齐 OpenAI / Anthropic vision API：content 既可以是字符串（老用法），
# 也可以是 ContentBlock 列表（多模态）。
#
# 红线（plan §2 新增）：
# ⛔ image / audio 走 URL 引用，不在 content 内嵌 base64 大字符串
# ⛔ provider 适配层负责把 ContentBlock 翻译成对应 vendor 格式


class _ImageUrl(BaseModel):
    url: str
    # auto: provider 自动选；low: 低分辨率省 token；high: 全分辨率
    detail: Literal["auto", "low", "high"] = "auto"


class _AudioUrl(BaseModel):
    url: str
    # mp3 / wav / m4a / ogg / flac ...
    format: str | None = None


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImageUrlBlock(BaseModel):
    type: Literal["image_url"] = "image_url"
    image_url: _ImageUrl


class AudioUrlBlock(BaseModel):
    type: Literal["audio_url"] = "audio_url"
    audio_url: _AudioUrl


ContentBlock = TextBlock | ImageUrlBlock | AudioUrlBlock


def normalize_content(content: str | list[ContentBlock] | list[dict[str, Any]]) -> list[ContentBlock]:
    """把任意形态 content 归一化为 list[ContentBlock]

    - str → [TextBlock]
    - list[ContentBlock] → 原样
    - list[dict] → 按 type 字段 dispatch（兼容外部 API 直接传 dict）
    """
    if isinstance(content, str):
        return [TextBlock(text=content)]
    out: list[ContentBlock] = []
    for item in content:
        if isinstance(item, TextBlock | ImageUrlBlock | AudioUrlBlock):
            out.append(item)
            continue
        if not isinstance(item, dict):
            raise ValueError(f"非法 ContentBlock 类型: {type(item).__name__}")
        t = item.get("type")
        if t == "text":
            out.append(TextBlock.model_validate(item))
        elif t == "image_url":
            out.append(ImageUrlBlock.model_validate(item))
        elif t == "audio_url":
            out.append(AudioUrlBlock.model_validate(item))
        else:
            raise ValueError(f"未知 ContentBlock type: {t!r}")
    return out


def flatten_to_text(content: str | list[ContentBlock]) -> str:
    """把多模态 content 摊平成纯文本（仅取 TextBlock）—— 给 messages.content 字段用（老消息消费者读纯文本 content）"""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for b in content:
        if isinstance(b, TextBlock):
            parts.append(b.text)
        elif isinstance(b, ImageUrlBlock):
            parts.append(f"[image:{b.image_url.url}]")
        elif isinstance(b, AudioUrlBlock):
            parts.append(f"[audio:{b.audio_url.url}]")
    return "".join(parts)


class Message(BaseModel):
    """通用消息载体（OpenAI 风格）

    P19.4 PR #40：content 既可以是字符串（老用法），也可以是 ContentBlock 列表
    （多模态）；provider 适配层用 normalize_content() / flatten_to_text() 兜底。
    """

    role: Role
    content: str | list[ContentBlock]
    name: str | None = None
    tool_call_id: str | None = None

    model_config = ConfigDict(extra="ignore")

    def text(self) -> str:
        """便捷：拿 content 的纯文本表示"""
        return flatten_to_text(self.content)

    def blocks(self) -> list[ContentBlock]:
        """便捷：拿归一化的 block 列表"""
        return normalize_content(self.content)

    @property
    def is_multimodal(self) -> bool:
        return isinstance(self.content, list) and any(
            not isinstance(b, TextBlock) for b in self.content
        )


class AgentDef(BaseModel):
    """注册表里一个 agent 的"身份证"

    config 字段 provider-specific：
      local:    {"module": "chameleon.agents.qwen_chat", "agent_class": "QwenChatAgent"}
      dify:      {"endpoint", "app_id", "api_key_env", "mode": "chat|workflow"}
      fastgpt:   {"endpoint", "app_id", "api_key_env"}
    """

    key: str
    provider: str
    description: str = ""
    version: str | None = None
    tags: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class InvokeContext(BaseModel):
    """每次调用打包好的上下文

    service 层从 DB / registry 取数据装配，喂给 Provider。
    """

    agent_def: AgentDef
    input: str | list[Message]
    history: list[Message] = Field(default_factory=list)
    # None = 无真实会话（如编辑器对话调试）；运行日志「会话」列显 —
    session_id: str | None = None
    provider_conv_id: str | None = None
    context_vars: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)
    app_id: str
    stream: bool = False
    request_id: str | None = None
    # Phase C：本次调用附带的附件原始 dict（同 attachments 入参形态），
    # 给本地 agent / Provider 透传；图/音已经由 service 层翻进 input 的 ContentBlock，
    # 这里给 agentkit 作者拿到 raw metadata（filename / mime / object_url）
    attachments: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class StepRecord(BaseModel):
    """中间步骤记录（节点 / 思考 / 工具调用编排等）"""

    name: str
    status: Literal["running", "success", "failed"] = "success"
    duration_ms: int | None = None
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    thinking: str | None = None


class Citation(BaseModel):
    """知识引用"""

    source: str
    score: float | None = None
    snippet: str | None = None
    meta: dict[str, Any] | None = None


class ToolCallRecord(BaseModel):
    """工具调用记录"""

    name: str
    args: dict[str, Any] | None = None
    result: Any | None = None
    error: str | None = None


class Usage(BaseModel):
    """token 用量"""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class StreamEventType(StrEnum):
    """流式事件类型 —— 封闭枚举"""

    delta = "delta"  # 增量 token
    step = "step"  # 中间步骤
    citation = "citation"  # 引用
    tool_call = "tool_call"  # 工具调用记录
    tool_result = "tool_result"  # 工具结果
    metadata = "metadata"  # 元数据
    done = "done"  # 完成（data == InvokeResult.model_dump()）
    error = "error"  # 流中错误


class StreamEvent(BaseModel):
    """统一流式事件"""

    type: StreamEventType
    data: dict[str, Any] = Field(default_factory=dict)


class InvokeResult(BaseModel):
    """非流式调用结果（也是流式 done 事件的 data 体）"""

    answer: str = ""
    session_id: str
    request_id: str | None = None
    steps: list[StepRecord] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    usage: Usage | None = None
    provider_conv_id: str | None = None  # provider 端的会话 ID（双写用）
    raw: dict[str, Any] | None = None  # 仅 DEBUG 模式填充


# ── 收集器：把 stream 事件聚合成 InvokeResult（base 提供，provider 默认实现用）─


class _StreamAggregator:
    """累积 stream 事件 → InvokeResult"""

    def __init__(self, session_id: str, request_id: str | None) -> None:
        self.session_id = session_id
        self.request_id = request_id
        self.answer_chunks: list[str] = []
        # 按 name 索引，last-write-wins —— 流式期 running → success 两个事件折叠成
        # 一条最终态；非流式聚合时客户端拿到的 steps 数组无重复。插入顺序保留。
        self._steps: dict[str, StepRecord] = {}
        self.citations: list[Citation] = []
        self.tool_calls: list[ToolCallRecord] = []
        self.usage: Usage | None = None
        self.provider_conv_id: str | None = None
        self._done_data: dict[str, Any] | None = None

    @property
    def steps(self) -> list[StepRecord]:
        return list(self._steps.values())

    def feed(self, event: StreamEvent) -> None:
        if event.type == StreamEventType.delta:
            chunk = event.data.get("text", "")
            if chunk:
                self.answer_chunks.append(chunk)
        elif event.type == StreamEventType.step:
            step = StepRecord.model_validate(event.data)
            # 同名节点 running → success 两个事件折叠：保留有 duration_ms 的最终态，
            # 缺则保留最新一条；插入顺序按首见 name 保留
            self._steps[step.name] = step
        elif event.type == StreamEventType.citation:
            self.citations.append(Citation.model_validate(event.data))
        elif event.type == StreamEventType.tool_call:
            self.tool_calls.append(ToolCallRecord.model_validate(event.data))
        elif event.type == StreamEventType.tool_result:
            # 把 tool_result 合并到最近的 tool_call（按 name 匹配）；找不到则追加新条目
            name = event.data.get("name")
            for tc in reversed(self.tool_calls):
                if tc.name == name and tc.result is None:
                    tc.result = event.data.get("result")
                    return
            self.tool_calls.append(
                ToolCallRecord(name=name or "", result=event.data.get("result"))
            )
        elif event.type == StreamEventType.metadata:
            if "usage" in event.data:
                self.usage = Usage.model_validate(event.data["usage"])
            if "provider_conv_id" in event.data:
                self.provider_conv_id = event.data["provider_conv_id"]
        elif event.type == StreamEventType.done:
            self._done_data = event.data

    def result(self) -> InvokeResult:
        """合并累积 + done 数据：done 字段非空时覆盖，否则用累积值

        意图：每个 provider 都按"流中 done 是终态"约定 emit，但 done 字段空
              ↔ "用累积值"。这给 provider 写起来最大灵活度（DIFY 答案靠 delta
              累积；LangGraph 在 chain_end 才知道完整答案；FastGPT 类似）。
        """
        accumulated = {
            "answer": "".join(self.answer_chunks),
            "session_id": self.session_id,
            "request_id": self.request_id,
            "steps": [s.model_dump() for s in self.steps],
            "citations": [c.model_dump() for c in self.citations],
            "tool_calls": [tc.model_dump() for tc in self.tool_calls],
            "usage": self.usage.model_dump() if self.usage else None,
            "provider_conv_id": self.provider_conv_id,
        }
        if self._done_data is not None:
            for k, v in self._done_data.items():
                # 非 None 且非空字符串 / 非空 list → done 字段优先
                if v is None:
                    continue
                if isinstance(v, str) and not v:
                    continue
                if isinstance(v, list) and not v:
                    continue
                accumulated[k] = v
        return InvokeResult.model_validate(accumulated)
