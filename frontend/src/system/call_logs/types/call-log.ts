import type { EntityId } from '@/core/types/api';

export interface CallLogItem {
  id: EntityId;
  request_id: string;
  app_id: string;
  agent_key: string;
  api_key_id?: EntityId | null;
  session_id: string | null;
  stream: boolean;
  success: boolean;
  code: number;
  error_class?: string | null;
  error_message: string | null;
  duration_ms: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  created_at: string;
}

export interface SpanRecord {
  name: string;
  start_ms: number;
  end_ms: number;
  status: 'success' | 'failed' | 'running' | string;
  error_class?: string | null;
  error_message?: string | null;
  meta?: Record<string, unknown> | null;
}

export interface CallLogDetail extends CallLogItem {
  spans: SpanRecord[] | null;
  request_payload: Record<string, unknown> | null;
  response_payload: Record<string, unknown> | null;
}
