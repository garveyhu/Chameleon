import { get } from '@/core/lib/request';
import type {
  OverviewItem,
  TimeSeriesResult,
  TopAgent,
  TopApp,
} from '@/system/dashboard/types/dashboard';

export interface RangeParams {
  from_ts?: string;
  to_ts?: string;
}

export const dashboardApi = {
  overview: (params?: RangeParams) =>
    get<OverviewItem>('/v1/admin/dashboard/overview', { params }),
  timeseries: (
    params?: { granularity?: 'hour' | 'day' | 'auto'; hours?: number } & RangeParams,
  ) => get<TimeSeriesResult>('/v1/admin/dashboard/timeseries', { params }),
  topAgents: (params?: { limit?: number; hours?: number } & RangeParams) =>
    get<TopAgent[]>('/v1/admin/dashboard/top-agents', { params }),
  topApps: (params?: { limit?: number; hours?: number } & RangeParams) =>
    get<TopApp[]>('/v1/admin/dashboard/top-apps', { params }),
};
