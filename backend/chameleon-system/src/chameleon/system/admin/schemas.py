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
