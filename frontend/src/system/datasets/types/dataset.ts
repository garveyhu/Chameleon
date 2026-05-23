import type { EntityId } from '@/core/types/api';

export interface DatasetItem {
  id: EntityId;
  name: string;
  description: string | null;
  item_count: number;
  created_at: string;
  updated_at: string;
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
