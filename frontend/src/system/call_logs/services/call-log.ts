import { get } from '@/core/lib/request';
import type { PageResult } from '@/core/types/api';
import type { CallLogItem } from '@/system/call_logs/types/call-log';

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
};
