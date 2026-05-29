"""admin 模块 DTO"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from chameleon.system.scores.schemas import ScoreItem


class CallLogItem(BaseModel):
    id: int
    request_id: str
    app_id: str
    agent_key: str
    session_id: str | None
    stream: bool
    success: bool
    code: int
    error_message: str | None
    duration_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    # 会话账本维度：渠道 / 模型 / 成本 / 归属
    channel: str | None = None
    model_code: str | None = None
    cost_usd: float | None = None
    api_key_id: int | None = None
    # api_key 展示名（join api_keys 推导；无 key 调用为 None）
    api_key_name: str | None = None
    # 会话标题（join sessions.title 推导；无会话 / 未命名为 None）
    session_title: str | None = None
    # 列表内联输入/输出预览（根行 payload 抽取的短文本，LangSmith 式 Input/Output 列）
    input_preview: str | None = None
    output_preview: str | None = None
    user_id: int | None = None
    # 编排方式推导（join agents.source；source=graph 时 join graphs.kind）：
    # source ∈ local / graph / dify / fastgpt / ...；kind ∈ chatflow / workflow / None
    source: str | None = None
    kind: str | None = None
    # P17.C1 嵌套 Observation
    parent_id: str | None = None
    observation_type: str = "generation"
    completion_start_ms: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CallLogDetailItem(CallLogItem):
    """call_log 详情：列表 fields + 完整 spans / request_payload / response_payload"""

    spans: list | None = None
    request_payload: dict | None = None
    response_payload: dict | None = None


class TraceTreeNode(BaseModel):
    """Trace tree 节点 —— observation 嵌套树的一个节点

    每个节点是一条 call_log；children 列表里是 parent_id == 本 node.request_id 的子。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: str
    parent_id: str | None = None
    observation_type: str = "generation"
    agent_key: str
    app_id: str
    session_id: str | None = None
    stream: bool = False
    success: bool
    code: int
    error_message: str | None = None
    duration_ms: int
    completion_start_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    # 本节点自身 cost（不含子）
    cost_usd: float | None = None
    created_at: datetime
    scores: list[ScoreItem] = []
    children: list["TraceTreeNode"] = []
    # P23.C2 subtree 累加（含自身 + 所有后代）—— 由 aggregator 回填
    rollup_cost_usd: float | None = None
    rollup_prompt_tokens: int = 0
    rollup_completion_tokens: int = 0
    rollup_total_tokens: int = 0


class ProviderStatusItem(BaseModel):
    name: str
    ok: bool
    error: str | None = None


class SessionItem(BaseModel):
    """会话（thread）列表项 —— 按 ChatSession 维度（多轮对话一条），区别于 trace（单次运行）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    agent_key: str
    app_id: str
    end_user_id: str | None = None
    # 渠道由 call_logs 根行派生（embed / playground / api / openai / internal）
    channel: str | None = None
    title: str | None = None
    turn_count: int = 0  # 该会话的消息条数
    last_message_at: datetime | None = None
    created_at: datetime
