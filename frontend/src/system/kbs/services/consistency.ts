import { get, post } from '@/core/lib/request';
import type { EntityId } from '@/core/types/api';
import type { ConsistencyReportItem } from '@/system/kbs/types/consistency';

export const consistencyApi = {
  scan: (kbId: EntityId) =>
    post<ConsistencyReportItem>(
      `/v1/admin/kbs/${kbId}/consistency-reports/scan`,
    ),
  list: (kbId: EntityId, limit = 50) =>
    get<ConsistencyReportItem[]>(
      `/v1/admin/kbs/${kbId}/consistency-reports`,
      { params: { limit } },
    ),
  get: (kbId: EntityId, reportId: EntityId) =>
    get<ConsistencyReportItem>(
      `/v1/admin/kbs/${kbId}/consistency-reports/${reportId}`,
    ),
  repair: (kbId: EntityId, reportId: EntityId) =>
    post<ConsistencyReportItem>(
      `/v1/admin/kbs/${kbId}/consistency-reports/${reportId}/repair`,
    ),
};
