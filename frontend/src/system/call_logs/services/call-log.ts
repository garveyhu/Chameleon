import { get, post } from '@/core/lib/request';
import type { EntityId, PageResult } from '@/core/types/api';
import type {
  CallLogDetail,
  CallLogItem,
  ScoreDataType,
  ScoreItem,
  ScoreSource,
  TraceTreeNode,
} from '@/system/call_logs/types/call-log';

export interface CreateScorePayload {
  call_log_id: string;
  trace_id?: string | null;
  name: string;
  value?: number | null;
  string_value?: string | null;
  data_type: ScoreDataType;
  source?: ScoreSource;
  comment?: string | null;
}

export const callLogApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    app_id?: string;
    agent_key?: string;
    channel?: string;
    model_code?: string;
    session_id?: string;
    success?: boolean;
    since?: string;
    until?: string;
  }) => get<PageResult<CallLogItem>>('/v1/admin/call-logs', { params }),

  get: (id: EntityId) => get<CallLogDetail>(`/v1/admin/call-logs/${id}`),

  /** P17.C1：按 request_id 取嵌套 observation 树（含 scores） */
  tree: (requestId: string) =>
    get<TraceTreeNode>(`/v1/admin/call-logs/${encodeURIComponent(requestId)}/tree`),
};

export const scoreApi = {
  /** 按 call_log_id 或 trace_id 列 scores（两者必传其一） */
  list: (params: { call_log_id?: string; trace_id?: string }) =>
    get<ScoreItem[]>('/v1/admin/scores', { params }),

  create: (payload: CreateScorePayload) =>
    post<ScoreItem>('/v1/admin/scores', payload),
};
