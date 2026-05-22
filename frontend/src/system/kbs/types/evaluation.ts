import type { EntityId } from '@/core/types/api';
import type { RecallMode } from '@/system/kbs/types/kb';

export type EvaluationStatus = 'pending' | 'running' | 'done' | 'failed';

export interface EvaluationQuery {
  query: string;
  expected_chunk_ids: EntityId[];
}

export interface EvaluationPerQuery {
  query: string;
  hits: EntityId[];
  expected: EntityId[];
  first_hit_rank: number | null;
  latency_ms: number;
}

export interface EvaluationResults {
  hit_at_k: Record<string, number>;
  mrr: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  per_query: EvaluationPerQuery[];
}

export interface Evaluation {
  id: EntityId;
  kb_id: EntityId;
  name: string;
  recall_mode: RecallMode;
  top_k: number;
  status: EvaluationStatus;
  error_message: string | null;
  results: EvaluationResults | null;
  created_at: string;
  completed_at: string | null;
}

export interface EvaluationListItem {
  id: EntityId;
  kb_id: EntityId;
  name: string;
  recall_mode: RecallMode;
  top_k: number;
  status: EvaluationStatus;
  created_at: string;
  completed_at: string | null;
  hit_at_5: number | null;
  mrr: number | null;
  latency_p50_ms: number | null;
}

export interface CreateEvaluationRequest {
  name: string;
  queries: EvaluationQuery[];
  recall_mode: RecallMode;
  top_k: number;
}
