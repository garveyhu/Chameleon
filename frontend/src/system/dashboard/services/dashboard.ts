import { get } from '@/core/lib/request';
import type {
  CostDimensionRow,
  CostTimeseriesPoint,
  CostTotalsResult,
  DimensionKey,
  DistributionRow,
  OverviewItem,
  TimeSeriesResult,
  TopDimensionRow,
} from '@/system/dashboard/types/dashboard';

/** 统一时间区间入参（两 tab 共用，口径一致） */
export interface RangeParams {
  from_ts?: string;
  to_ts?: string;
}

const BASE = '/v1/admin/dashboard';

export const dashboardApi = {
  overview: (params?: RangeParams) =>
    get<OverviewItem>(`${BASE}/overview`, { params }),
  timeseries: (
    params?: RangeParams & { granularity?: 'hour' | 'day' | 'auto' },
  ) => get<TimeSeriesResult>(`${BASE}/timeseries`, { params }),
  /** 通用维度 top-N（替代旧的 top-agents / top-apps） */
  topDimension: (
    params: RangeParams & { dimension: DimensionKey; limit?: number },
  ) => get<TopDimensionRow[]>(`${BASE}/top-dimension`, { params }),
  /** 单维分布（渠道 / 错误类型 / 模型 等）：count + cost */
  distribution: (
    params: RangeParams & { dimension: DimensionKey; limit?: number },
  ) => get<DistributionRow[]>(`${BASE}/distribution`, { params }),

  costTotals: (params?: RangeParams) =>
    get<CostTotalsResult>(`${BASE}/cost/totals`, { params }),
  costByDimension: (
    params: RangeParams & { dimension: DimensionKey; limit?: number },
  ) => get<CostDimensionRow[]>(`${BASE}/cost/by-dimension`, { params }),
  costTimeseries: (params?: RangeParams & { bucket?: 'hour' | 'day' }) =>
    get<CostTimeseriesPoint[]>(`${BASE}/cost/timeseries`, { params }),
};
