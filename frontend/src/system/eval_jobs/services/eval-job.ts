import { get, post } from '@/core/lib/request';
import type { EntityId, PageResult } from '@/core/types/api';
import type {
  CreateEvalJobPayload,
  EvalJobItem,
  EvalJobRunItem,
  TriggerEvalJobResult,
  UpdateEvalJobPayload,
} from '@/system/eval_jobs/types/eval-job';

const BASE = '/v1/admin/eval-jobs';

export const evalJobApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    keyword?: string;
    sort_by?: string;
    order?: string;
    enabled?: boolean;
  }) => get<PageResult<EvalJobItem>>(BASE, { params }),

  get: (id: EntityId) => get<EvalJobItem>(`${BASE}/${id}`),

  create: (payload: CreateEvalJobPayload) =>
    post<EvalJobItem>(BASE, payload),

  update: (id: EntityId, payload: UpdateEvalJobPayload) =>
    post<EvalJobItem>(`${BASE}/${id}/update`, payload),

  delete: (id: EntityId) => post<null>(`${BASE}/${id}/delete`, {}),

  trigger: (id: EntityId) =>
    post<TriggerEvalJobResult>(`${BASE}/${id}/trigger`, {}),

  listRuns: (id: EntityId, limit = 50) =>
    get<EvalJobRunItem[]>(`${BASE}/${id}/runs`, {
      params: { limit },
    }),
};
