"""Provider 抽象层的核心数据类型

四件套：AgentDef / InvokeContext / StreamEvent / InvokeResult
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["user", "assistant", "system", "tool"]


class Message(BaseModel):
    """通用消息载体（OpenAI 风格）"""

    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None

    model_config = ConfigDict(extra="ignore")


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


class ChannelOverride(BaseModel):
    """运行时 channel 凭证注入（P17.A1.2 矩阵路由解析后写入）

    存在时 HTTP provider（dify/fastgpt）应**优先**用这里的 base_url +
    api_key（明文，service 层已经解密），跳过 agent_def.config 里
    api_key_env 等老路径。channel_id 用于 failover 标识。
    """

    channel_id: int
    base_url: str | None = None
    api_key: str | None = None

    model_config = ConfigDict(frozen=True)


class InvokeContext(BaseModel):
    """每次调用打包好的上下文

    service 层从 DB / registry 取数据装配，喂给 Provider。
    """

    agent_def: AgentDef
    input: str | list[Message]
    history: list[Message] = Field(default_factory=list)
    session_id: str
    provider_conv_id: str | None = None
    context_vars: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)
    app_id: str
    stream: bool = False
    request_id: str | None = None
    # P17.A1.2 矩阵路由解析后的 channel 凭证；None 表示走老路径（agent.config 直绑）
    channel_override: ChannelOverride | None = None

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
        self.steps: list[StepRecord] = []
        self.citations: list[Citation] = []
        self.tool_calls: list[ToolCallRecord] = []
        self.usage: Usage | None = None
        self.provider_conv_id: str | None = None
        self._done_data: dict[str, Any] | None = None

    def feed(self, event: StreamEvent) -> None:
        if event.type == StreamEventType.delta:
            chunk = event.data.get("text", "")
            if chunk:
                self.answer_chunks.append(chunk)
        elif event.type == StreamEventType.step:
            self.steps.append(StepRecord.model_validate(event.data))
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
