import { get, post } from '@/core/lib/request';
import type { EntityId, PageResult } from '@/core/types/api';
import type {
  BulkImportRequest,
  BulkImportResult,
  CompareRunsResult,
  CreateDatasetRequest,
  DatasetItem,
  DatasetItemRow,
  DatasetRunDetail,
  DatasetRunItemRow,
  DatasetRunRow,
  SampleFromLogsRequest,
  SampleResult,
  ScoreDistributionResult,
  UpdateItemRequest,
} from '@/system/datasets/types/dataset';

const BASE = '/v1/admin/datasets';

export const datasetApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    keyword?: string;
    sort_by?: string;
    order?: string;
  }) => get<PageResult<DatasetItem>>(BASE, { params }),
  get: (id: EntityId) => get<DatasetItem>(`${BASE}/${id}`),
  create: (req: CreateDatasetRequest) => post<DatasetItem>(BASE, req),
  update: (id: EntityId, req: Partial<CreateDatasetRequest>) =>
    post<DatasetItem>(`${BASE}/${id}/update`, req),
  delete: (id: EntityId) => post<void>(`${BASE}/${id}/delete`),
  listItems: (id: EntityId, limit = 200) =>
    get<DatasetItemRow[]>(`${BASE}/${id}/items`, { params: { limit } }),
  sampleFromLogs: (id: EntityId, req: SampleFromLogsRequest) =>
    post<SampleResult>(`${BASE}/${id}/sample-from-logs`, req),
  bulkImport: (id: EntityId, req: BulkImportRequest) =>
    post<BulkImportResult>(`${BASE}/${id}/items/bulk-import`, req),
  /** 人工标注：改某 item 的 expected_output / meta */
  updateItem: (itemId: EntityId, req: UpdateItemRequest) =>
    post<DatasetItemRow>(`${BASE}/items/${itemId}/update`, req),

  // ── runs（实验运行）—— 接出已就绪的 5 个端点 ──
  listRuns: (datasetId: EntityId) =>
    get<DatasetRunRow[]>(`${BASE}/${datasetId}/runs`),
  getRun: (runId: EntityId) => get<DatasetRunDetail>(`${BASE}/runs/${runId}`),
  listRunItems: (runId: EntityId) =>
    get<DatasetRunItemRow[]>(`${BASE}/runs/${runId}/items`),
  compareRuns: (runIds: EntityId[]) =>
    post<CompareRunsResult>(`${BASE}/runs/compare`, { run_ids: runIds }),
  scoreDistribution: (runId: EntityId, threshold = 0.5, buckets = 10) =>
    get<ScoreDistributionResult>(`${BASE}/runs/${runId}/score-distribution`, {
      params: { threshold, buckets },
    }),
};
