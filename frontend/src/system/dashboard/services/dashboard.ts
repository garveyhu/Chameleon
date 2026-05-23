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

// P22.1 Cost dashboard
export type CostDimension = 'agent_key' | 'app_id' | 'session_id';

export interface CostTotalsResult {
  range_from: string;
  range_to: string;
  total_usd: number;
  prev_total_usd: number | null;
  delta_pct: number | null;
  total_calls: number;
}

export interface CostDimensionRow {
  label: string;
  cost_usd: number;
  calls: number;
}

export interface CostTimeseriesPoint {
  ts: string;
  cost_usd: number;
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

  costTotals: (params?: { hours?: number } & RangeParams) =>
    get<CostTotalsResult>('/v1/admin/dashboard/cost/totals', { params }),
  costByDimension: (
    params: {
      dimension: CostDimension;
      hours?: number;
      limit?: number;
    } & RangeParams,
  ) =>
    get<CostDimensionRow[]>('/v1/admin/dashboard/cost/by-dimension', {
      params,
    }),
  costTimeseries: (
    params?: { hours?: number; bucket?: 'hour' | 'day' } & RangeParams,
  ) =>
    get<CostTimeseriesPoint[]>('/v1/admin/dashboard/cost/timeseries', {
      params,
    }),
};
