"""datasets DTO"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field


class CategoryDef(BaseModel):
    """数据集能力维度定义（对比雷达的轴 + 样本归类的可选值）。"""

    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=500)


class ClassifyItemsResult(BaseModel):
    """AI 批量归类结果。"""

    updated: int


class SuggestCategoriesRequest(BaseModel):
    """AI 建议能力维度入参（无状态，创建/编辑都用表单值）。"""

    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    system_prompt: str | None = Field(default=None, max_length=20000)


class DatasetItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    # 数据集级默认系统提示词（如 text2sql 的 schema）；评估运行作被测模型 system 默认值
    system_prompt: str | None = None
    # 能力维度定义（样本归类 + 对比雷达轴）；空 = 未配置
    categories: list[CategoryDef] | None = None
    item_count: int
    run_count: int = 0
    last_run_score: float | None = None
    created_at: datetime
    updated_at: datetime


class DatasetDetail(DatasetItem):
    """详情同列表项（v0.4 暂无额外字段）"""

    pass


class CreateDatasetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    system_prompt: str | None = Field(default=None, max_length=20000)
    categories: list[CategoryDef] | None = None


class UpdateDatasetRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    system_prompt: str | None = Field(default=None, max_length=20000)
    categories: list[CategoryDef] | None = None


class DatasetItemItem(BaseModel):
    """dataset_items 出参（已脱敏）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    source_call_log_id: str | None = None
    input_payload: dict[str, Any]
    expected_output: dict[str, Any] | None = None
    # 模块 G：GSB 参照回答（区别 expected_output 金标准语义）
    reference_output: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    # 样本备注：描述这条样本用于评测什么（自由文本，可空）
    note: str | None = None
    # 能力维度归类：指向数据集 categories 的某 key（单维度，可空 = 未分类）
    category: str | None = None
    created_at: datetime
    updated_at: datetime


class SampleFromLogsRequest(BaseModel):
    """按 filter 采样 call_log → dataset_items（默认脱敏）"""

    app_id: str | None = None
    agent_key: str | None = None
    success: bool | None = None
    since: datetime | None = None
    until: datetime | None = None
    # 仅采前 N 条；默认 50，最大 500
    limit: int = Field(default=50, ge=1, le=500)
    # 是否同时把 response_payload 也带入 expected_output（人工标注前的"金标准"）
    include_response_as_expected: bool = True
    # P21.1 红线：PII 策略
    # - mask：preview / expected_output 内的 email/phone/id_card 替换占位符（默认）
    # - drop：含任意 PII 的 call_log 整条跳过，不入库
    # - keep：保留原文（明确知道无 PII 时；不推荐）
    pii_strategy: str = Field(default="mask", pattern="^(mask|drop|keep)$")


class SampleResult(BaseModel):
    """采样结果摘要"""

    dataset_id: int
    added: int
    skipped: int  # 已存在（同 source_call_log_id）跳过的数量
    # P21.1：因 PII drop 策略跳过的数量（与 skipped 区分）
    dropped_pii: int = 0
    # A3：本次采样新建的 item id 列表，供前端「撤销这批采样」批量删
    created_item_ids: list[int] = Field(default_factory=list)


class SampleCandidate(BaseModel):
    """采样预览候选：脱敏后的 input/expected 纯文本 + 来源/元信息，供前端评审编辑。"""

    source_call_log_id: str
    user_input: str
    answer: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class SamplePreviewResult(BaseModel):
    """采样预览结果：候选列表（不落库）+ 跳过统计。挑选/编辑后走 bulk-import 入库。"""

    candidates: list[SampleCandidate] = Field(default_factory=list)
    skipped: int = 0
    dropped_pii: int = 0


class BatchDeleteItemsRequest(BaseModel):
    """A2：批量删除样本"""

    item_ids: list[int] = Field(min_length=1, max_length=1000)


class BatchDeleteItemsResult(BaseModel):
    deleted: int


class UpdateItemRequest(BaseModel):
    """样本编辑：改 input_payload / expected_output / meta / note"""

    input_payload: dict[str, Any] | None = None
    expected_output: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    # 备注；传 None 不动，传 "" 清空，传文本覆盖（service 区分 None vs 空串）
    note: str | None = None
    # 能力维度归类；同 note 的 None/空串语义
    category: str | None = None


class CreateItemRequest(BaseModel):
    """电子表格「+新增行」单条样本入参（H2）

    与 bulk-import 一致：默认 mask PII（手填可能含邮箱/手机号）。
    input_payload 必填，expected_output / meta / note 可选。
    """

    input_payload: dict[str, Any]
    expected_output: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    note: str | None = None
    category: str | None = None
    # 同 sample / bulk-import：mask（默认）/ drop / keep
    pii_strategy: str = Field(default="mask", pattern="^(mask|drop|keep)$")


class BulkImportItem(BaseModel):
    """手工 import 时单条 item 的入参（前端解析 CSV/JSONL 后构造）"""

    input_payload: dict[str, Any]
    expected_output: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    note: str | None = None
    category: str | None = None


class BulkImportRequest(BaseModel):
    """批量 import items"""

    items: list[BulkImportItem] = Field(min_length=1, max_length=1000)
    # 同 sample：mask（默认）/ drop / keep
    pii_strategy: str = Field(default="mask", pattern="^(mask|drop|keep)$")


class BulkImportResult(BaseModel):
    dataset_id: int
    added: int
    dropped_pii: int = 0


class AiGenStreamRequest(BaseModel):
    """流式 AI 扩样：任务描述 + 生成数量"""

    task_description: str = Field(min_length=1, max_length=500)
    count: int = Field(default=5, ge=1, le=50)


class CandidatePayload(BaseModel):
    """单条候选载荷（流式产出 / 单条优化入参的 candidate 内联）"""

    user_input: str
    answer: str | None = None
    # AI 扩样产出的样本备注（说明该候选评测什么），导入时落到 item.note
    note: str | None = None
    # AI 自动归类的能力维度 key（来自数据集 categories），导入落 item.category
    category: str | None = None


class RefineCandidateRequest(BaseModel):
    """单条 AI 优化 / 重新生成"""

    task_description: str = Field(min_length=1, max_length=500)
    candidate: CandidatePayload
    instruction: str | None = Field(default=None, max_length=500)
    mode: str = Field(pattern="^(optimize|regenerate)$")


class RefinedCandidate(BaseModel):
    """单条优化 / 重新生成产出"""

    user_input: str
    answer: str | None = None
    note: str | None = None
    category: str | None = None


class OptimizeResult(BaseModel):
    """H3 智能优化产出：低分共性 → 重写 prompt + 报告"""

    run_id: int
    original_prompt: str
    optimized_prompt: str
    report: str
    weak_count: int


# ── DatasetRun（PR #25） ──────────────────────────────────


class DatasetRunRequest(BaseModel):
    """跑一次 dataset"""

    name: str = Field(min_length=1, max_length=128)
    model_override: str | None = Field(default=None, max_length=64)
    prompt_override: str | None = None
    judge: str = Field(default="exact_match", max_length=32)
    # 模块 G：judge 多模式参数（criteria / dsl 文本 / gsb 参照源开关等）；按 judge 分派解析
    judge_config: dict[str, Any] | None = None
    # P21.2：可选 EvalTemplate 联动；跑完后按 template metrics 评分
    eval_template_id: int | None = None
    # A3：被测对象设为 agent（含 graph 编排的）；设了则整条工作流当被测，忽略 model_override
    agent_key: str | None = Field(default=None, max_length=64)
    # 可选「归属 Key」：把本次评测的 token/成本/trace 计到该 API Key 名下单独统计。
    # 评测本是后台内部流量、不经 Key，传入仅用于归属盖章（前端按雪花精度以字符串传，
    # Pydantic 自动转 int，服务端无精度问题）。
    api_key_id: int | None = None


class DatasetRunItemRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_run_id: int
    dataset_item_id: int
    # Phase C：本 item 这次执行的 request_id —— 样本详情据此下钻到真实 LLM 调用
    # trace（/traces/{request_id}）。旧数据为 None（迁移前未落库）。
    request_id: str | None = None
    actual_output: dict[str, Any] | None = None
    score: float | None = None
    # 模块 G：评分理由 / 逐字段评分 / GSB 参照
    score_reason: str | None = None
    field_scores: dict[str, Any] | None = None
    reference_output: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    duration_ms: int | None = None


class DatasetRunItemDetail(DatasetRunItemRow):
    """运行详情逐样本明细：join dataset_item 带回输入/预期，省前端二次拉全样本。

    模块 E 用于运行详情抽屉的样本明细表 + 三栏对比（理想/模型/理由）。
    score_reason / field_scores 待模块 G 接入 judge 多模式后再补字段。
    """

    input_preview: str | None = None
    input_payload: dict[str, Any] | None = None
    expected_output: dict[str, Any] | None = None


class DatasetRunRow(BaseModel):
    """列表项

    H3 版本链：透 parent_run_id（是否优化产物）+ has_optimization 轻量标记
    （是否被优化过）；完整 optimized_prompt 不进列表，仅 DatasetRunDetail 返。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    name: str
    model_override: str | None = None
    judge: str
    # 本次评分配置（criteria / judge_model 等）；详情据此展示裁判模型 + 评分要点
    judge_config: dict[str, Any] | None = None
    status: str
    summary: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    # H3：本 run 由哪个 run 优化而来（自引用版本链；父 run 已删则为 None）
    parent_run_id: int | None = None
    # 从 ORM 读 optimized_prompt 仅用于推导 has_optimization，不进 JSON（exclude）
    optimized_prompt: str | None = Field(default=None, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_optimization(self) -> bool:
        """本 run 是否被优化过（optimized_prompt 非空）。"""
        return bool((self.optimized_prompt or "").strip())


class DatasetRunDetail(DatasetRunRow):
    """详情（含 prompt_override + 优化全文）"""

    agent_key: str | None = None
    prompt_override: str | None = None
    # 详情透优化全文 + 报告（覆盖列表的 exclude，列表只透 has_optimization 标记）
    optimized_prompt: str | None = None
    optimization_report: dict[str, Any] | None = None


class CompareRunsRequest(BaseModel):
    """对比 N 个 run 的 item-by-item 表"""

    run_ids: list[int] = Field(min_length=1, max_length=5)


class CompareItemCell(BaseModel):
    """每个对比单元：item + 各 run 的 score / actual"""

    dataset_item_id: int
    input_preview: str | None = None  # 已脱敏的展示文案
    expected_output: dict[str, Any] | None = None
    # 样本备注（考察点）；AI 分析上下文
    note: str | None = None
    # 能力维度归类 key（雷达据此分轴，取代前端关键词猜测）
    category: str | None = None
    cells: dict[int, DatasetRunItemRow] = Field(default_factory=dict)


class CompareRunsResult(BaseModel):
    runs: list[DatasetRunRow]
    rows: list[CompareItemCell]
    # 数据集配置的能力维度（雷达的轴）；空 = 未配置 → 前端不显示雷达
    categories: list[CategoryDef] | None = None


class CompareAnalysisResult(BaseModel):
    """运行对比的 AI 总结分析（markdown 文本）。"""

    analysis: str


# ── P21.2 评分分布 ────────────────────────────────────


class ScoreBucket(BaseModel):
    """[low, high) 区间桶"""

    low: float
    high: float
    count: int


class MetricDistribution(BaseModel):
    metric_name: str
    mean: float | None = None
    buckets: list[ScoreBucket]
    low_score_item_ids: list[int]  # 低于 threshold 或 <0.5 的 item id


class ScoreDistributionResult(BaseModel):
    run_id: int
    threshold: float = 0.5
    total_scored_items: int
    metrics: list[MetricDistribution]
