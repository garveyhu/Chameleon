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
  status: string;
  summary: Record<string, unknown> | null;
  error: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface DatasetRunDetail extends DatasetRunRow {
  agent_key: string | null;
  prompt_override: string | null;
}

export interface DatasetRunItemRow {
  id: EntityId;
  dataset_run_id: EntityId;
  dataset_item_id: EntityId;
  actual_output: Record<string, unknown> | null;
  score: number | null;
  error: Record<string, unknown> | null;
  duration_ms: number | null;
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
