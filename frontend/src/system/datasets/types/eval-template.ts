import type { EntityId } from '@/core/types/api';

export interface MetricSpec {
  name: string;
  algorithm: string;
  weight: number;
  threshold?: number | null;
  config?: Record<string, unknown> | null;
}

export interface EvalTemplateItem {
  id: EntityId;
  name: string;
  description: string | null;
  metrics: MetricSpec[];
  judge_provider: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface CreateEvalTemplateRequest {
  name: string;
  description?: string;
  metrics: MetricSpec[];
  judge_provider?: string;
}

export interface UpdateEvalTemplateRequest {
  description?: string;
  metrics?: MetricSpec[];
  judge_provider?: string;
}

// ── 评分分布 ────────────────────────────────────────────

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
