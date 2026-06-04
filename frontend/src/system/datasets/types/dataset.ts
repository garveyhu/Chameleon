import type { EntityId } from '@/core/types/api';

export interface DatasetItem {
  id: EntityId;
  name: string;
  description: string | null;
  item_count: number;
  created_at: string;
  updated_at: string;
  // P2 聚合（后端 list 补；老端点可能缺，故可选）
  run_count?: number;
  last_run_score?: number | null;
  /** 最近 N 次运行的 mean_score（老→新），给列表 sparkline */
  score_trend?: number[];
}

export interface DatasetItemRow {
  id: EntityId;
  dataset_id: EntityId;
  source_call_log_id: string | null;
  input_payload: Record<string, unknown>;
  expected_output: Record<string, unknown> | null;
  meta: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface CreateDatasetRequest {
  name: string;
  description?: string;
}

export type PiiStrategy = 'mask' | 'drop' | 'keep';

export interface SampleFromLogsRequest {
  app_id?: string;
  agent_key?: string;
  success?: boolean;
  since?: string;
  until?: string;
  limit?: number;
  include_response_as_expected?: boolean;
  pii_strategy?: PiiStrategy;
}

export interface SampleResult {
  dataset_id: EntityId;
  added: number;
  skipped: number;
  dropped_pii: number;
  /** A3：本次采样新建的 item id 列表，供「撤销这批采样」批量删 */
  created_item_ids: EntityId[];
}

/** A2：批量删除样本入参 / 结果 */
export interface BatchDeleteItemsRequest {
  item_ids: EntityId[];
}

export interface BatchDeleteItemsResult {
  deleted: number;
}

export interface BulkImportItem {
  input_payload: Record<string, unknown>;
  expected_output?: Record<string, unknown> | null;
  meta?: Record<string, unknown> | null;
}

export interface BulkImportRequest {
  items: BulkImportItem[];
  pii_strategy?: PiiStrategy;
}

export interface BulkImportResult {
  dataset_id: EntityId;
  added: number;
  dropped_pii: number;
}

// ── DatasetRun（实验运行）—— P2 接出已就绪的 runs 端点 ──────────

export interface DatasetRunRow {
  id: EntityId;
  dataset_id: EntityId;
  name: string;
  model_override: string | null;
  judge: string;
  judge_config: Record<string, unknown> | null;
  agent_key: string | null;
  status: string;
  summary: Record<string, unknown> | null;
  error: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  // H3 版本链：本 run 由哪个 run 优化而来（父已删则 null）；是否被优化过的轻量标记
  parent_run_id?: EntityId | null;
  has_optimization?: boolean;
}

export interface DatasetRunDetail extends DatasetRunRow {
  prompt_override: string | null;
  // H3：详情带优化全文 + 报告（列表只透 has_optimization 标记）
  optimized_prompt?: string | null;
  optimization_report?: Record<string, unknown> | null;
}

/** 手动发起运行入参 —— POST /v1/admin/datasets/{id}/run（同步，跑完才返回）。 */
export interface CreateDatasetRunRequest {
  name: string;
  judge: string;
  judge_config?: Record<string, unknown>;
  model_override?: string;
  agent_key?: string;
}

export interface DatasetRunItemRow {
  id: EntityId;
  dataset_run_id: EntityId;
  dataset_item_id: EntityId;
  /** Phase C：本 item 这次执行的 request_id，样本详情据此下钻到真实 LLM 调用 trace
   *  （/traces/{request_id}）；迁移前的旧运行为 null。 */
  request_id?: string | null;
  actual_output: Record<string, unknown> | null;
  score: number | null;
  error: Record<string, unknown> | null;
  duration_ms: number | null;
  // 运行详情明细 join 带回（compare 矩阵的 cells 不返，故可选）
  input_preview?: string | null;
  input_payload?: Record<string, unknown> | null;
  expected_output?: Record<string, unknown> | null;
  // 模块 G judge 升级后填评分理由；E 阶段后端暂不返 → undefined
  score_reason?: string | null;
  // 评分器逐项原始分：llm_score → {raw_1_5:n}；gsb → {verdict:'G'|'S'|'B'}
  field_scores?: Record<string, number | string | null> | null;
  // gsb 对照用的参照回答（原文 dict）
  reference_output?: Record<string, unknown> | null;
}

export interface CompareItemCell {
  dataset_item_id: EntityId;
  input_preview: string | null;
  expected_output: Record<string, unknown> | null;
  /** key = run_id（后端 dict[int] 序列化为 JSON object，key 是 string） */
  cells: Record<string, DatasetRunItemRow>;
}

export interface CompareRunsResult {
  runs: DatasetRunRow[];
  rows: CompareItemCell[];
}

export interface ScoreBucket {
  low: number;
  high: number;
  count: number;
}

export interface MetricDistribution {
  metric_name: string;
  mean: number | null;
  buckets: ScoreBucket[];
  low_score_item_ids: EntityId[];
}

export interface ScoreDistributionResult {
  run_id: EntityId;
  threshold: number;
  total_scored_items: number;
  metrics: MetricDistribution[];
}

/** 样本编辑：改 input_payload / expected_output / meta */
export interface UpdateItemRequest {
  input_payload?: Record<string, unknown> | null;
  expected_output?: Record<string, unknown> | null;
  meta?: Record<string, unknown> | null;
}

/** H2 电子表格「+新增行」：单条样本入参（input_payload 必填）。 */
export interface CreateItemRequest {
  input_payload: Record<string, unknown>;
  expected_output?: Record<string, unknown> | null;
  meta?: Record<string, unknown> | null;
  pii_strategy?: PiiStrategy;
}

/** H2：AI 扩样 —— 任务描述 + 生成数量 */
export interface AiGenerateRequest {
  task_description: string;
  count?: number;
}

export interface AiGenerateResult {
  dataset_id: EntityId;
  added: number;
}

/** H3：智能优化产出 —— 重写 prompt + 报告 + 前后对比 */
export interface OptimizeResult {
  run_id: EntityId;
  original_prompt: string;
  optimized_prompt: string;
  report: string;
  weak_count: number;
}
