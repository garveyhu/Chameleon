import type { EntityId } from '@/core/types/api';

export interface ConsistencyIssue {
  type: 'orphan_chunk' | 'dim_mismatch' | 'zero_vector' | string;
  chunk_id: number;
  kb_id: EntityId;
  reason: string;
}

export interface ConsistencyReportItem {
  id: EntityId;
  kb_id: EntityId;
  status: 'pending' | 'running' | 'done' | 'fixed' | 'failed' | string;
  issues: ConsistencyIssue[] | null;
  scanned_count: number;
  quarantined_count: number;
  fixed_count: number;
  error_message: string | null;
  started_at: string;
  finished_at: string | null;
}
