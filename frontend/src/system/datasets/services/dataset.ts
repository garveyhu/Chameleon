import { get, post } from '@/core/lib/request';
import type { EntityId } from '@/core/types/api';
import type {
  BulkImportRequest,
  BulkImportResult,
  CreateDatasetRequest,
  DatasetItem,
  DatasetItemRow,
  SampleFromLogsRequest,
  SampleResult,
} from '@/system/datasets/types/dataset';

export const datasetApi = {
  list: () => get<DatasetItem[]>('/v1/admin/datasets'),
  get: (id: EntityId) => get<DatasetItem>(`/v1/admin/datasets/${id}`),
  create: (req: CreateDatasetRequest) =>
    post<DatasetItem>('/v1/admin/datasets', req),
  update: (id: EntityId, req: Partial<CreateDatasetRequest>) =>
    post<DatasetItem>(`/v1/admin/datasets/${id}/update`, req),
  delete: (id: EntityId) =>
    post<void>(`/v1/admin/datasets/${id}/delete`),
  listItems: (id: EntityId, limit = 200) =>
    get<DatasetItemRow[]>(`/v1/admin/datasets/${id}/items`, {
      params: { limit },
    }),
  sampleFromLogs: (id: EntityId, req: SampleFromLogsRequest) =>
    post<SampleResult>(`/v1/admin/datasets/${id}/sample-from-logs`, req),
  bulkImport: (id: EntityId, req: BulkImportRequest) =>
    post<BulkImportResult>(
      `/v1/admin/datasets/${id}/items/bulk-import`,
      req,
    ),
};
