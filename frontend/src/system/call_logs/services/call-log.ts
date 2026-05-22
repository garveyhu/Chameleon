import { get } from '@/core/lib/request';
import type { EntityId, PageResult } from '@/core/types/api';
import type {
  CallLogDetail,
  CallLogItem,
  TraceTreeNode,
} from '@/system/call_logs/types/call-log';

export const callLogApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    app_id?: string;
    agent_key?: string;
    success?: boolean;
    since?: string;
    until?: string;
  }) => get<PageResult<CallLogItem>>('/v1/admin/call-logs', { params }),

  get: (id: EntityId) => get<CallLogDetail>(`/v1/admin/call-logs/${id}`),

  /** P17.C1：按 request_id 取嵌套 observation 树 */
  tree: (requestId: string) =>
    get<TraceTreeNode>(`/v1/admin/call-logs/${encodeURIComponent(requestId)}/tree`),
};
