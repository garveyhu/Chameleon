import { get } from '@/core/lib/request';
import type {
  OverviewItem,
  TimeSeriesResult,
  TopAgent,
  TopApp,
} from '@/system/dashboard/types/dashboard';

export const dashboardApi = {
  overview: () => get<OverviewItem>('/v1/admin/dashboard/overview'),
  timeseries: (params?: { granularity?: 'hour' | 'day'; hours?: number }) =>
    get<TimeSeriesResult>('/v1/admin/dashboard/timeseries', { params }),
  topAgents: (params?: { limit?: number; hours?: number }) =>
    get<TopAgent[]>('/v1/admin/dashboard/top-agents', { params }),
  topApps: (params?: { limit?: number; hours?: number }) =>
    get<TopApp[]>('/v1/admin/dashboard/top-apps', { params }),
};
