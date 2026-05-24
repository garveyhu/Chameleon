import { get } from '@/core/lib/request';
import type { CallLogDetail, TraceTreeNode } from '@/system/call_logs/types/call-log';

export const traceApi = {
  getTree: (requestId: string) =>
    get<TraceTreeNode>(`/v1/admin/call-logs/${requestId}/tree`),
  getNodeDetail: (id: string | number) =>
    get<CallLogDetail>(`/v1/admin/call-logs/${id}`),
};
