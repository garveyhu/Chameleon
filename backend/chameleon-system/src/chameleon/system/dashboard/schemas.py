"""dashboard DTO（请求/响应模型）

所有指标统一区间口径：跟随调用方传入的 [range_from, range_to]，不再写死 24h/7d。
聚合一律只算 trace 根行（parent_id IS NULL），与 call_logs 的 cost rollup 对齐，
避免把子 generation/span 行重复累加导致 token/计数虚高。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class OverviewItem(BaseModel):
    """综合概览卡片数据（全部区间口径 + 上一周期 delta）。"""

    range_from: datetime
    range_to: datetime
    # 流量
    total_calls: int
    prev_period_calls: int
    # 健康
    success_rate: float
    prev_success_rate: float | None = None
    avg_duration_ms: float
    # token（提示/完成/合计）
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    # 活跃实体
    active_apps: int
    active_agents: int
    active_end_users: int
    # 流式调用占比
    stream_ratio: float
    # P95 响应延迟（percentile_cont，仅 PG；SQLite 测试库降级为 None）
    p95_duration_ms: float | None = None
    # 首字延迟（avg completion_start_ms，仅有该值的行参与；无则 None）
    ttft_avg_ms: float | None = None


class TimePoint(BaseModel):
    ts: datetime
    total: int
    errors: int


class TimeSeriesResult(BaseModel):
    granularity: str
    points: list[TimePoint]


class TopDimensionRow(BaseModel):
    """通用维度 top-N 行（替代 TopAgent/TopApp 两个单维 DTO）。"""

    label: str
    display_name: str | None = None
    count: int


class CostTotalsResult(BaseModel):
    """成本卡片总额 + 上一周期 delta。"""

    range_from: datetime
    range_to: datetime
    total_usd: float
    prev_total_usd: float | None = None
    delta_pct: float | None = None
    total_calls: int
    total_tokens: int


class CostDimensionRow(BaseModel):
    """按维度聚合的成本明细行。"""

    label: str
    display_name: str | None = None
    cost_usd: float
    calls: int
    success_calls: int
    total_tokens: int


class CostTimeseriesPoint(BaseModel):
    ts: datetime
    cost_usd: float
    total_tokens: int = 0


class DistributionRow(BaseModel):
    """分布统计行（渠道 / 错误类型 / 模型 等单值分布）。"""

    label: str
    display_name: str | None = None
    count: int
    cost_usd: float
