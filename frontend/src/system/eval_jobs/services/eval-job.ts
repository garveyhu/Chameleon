import { get, post } from '@/core/lib/request';
import type { EntityId } from '@/core/types/api';
import type {
  CreateEvalJobPayload,
  EvalJobItem,
  EvalJobRunItem,
  TriggerEvalJobResult,
  UpdateEvalJobPayload,
} from '@/system/eval_jobs/types/eval-job';

export const evalJobApi = {
  list: () => get<EvalJobItem[]>('/v1/admin/eval-jobs'),

  get: (id: EntityId) => get<EvalJobItem>(`/v1/admin/eval-jobs/${id}`),

  create: (payload: CreateEvalJobPayload) =>
    post<EvalJobItem>('/v1/admin/eval-jobs', payload),

  update: (id: EntityId, payload: UpdateEvalJobPayload) =>
    post<EvalJobItem>(`/v1/admin/eval-jobs/${id}/update`, payload),

  delete: (id: EntityId) =>
    post<null>(`/v1/admin/eval-jobs/${id}/delete`, {}),

  trigger: (id: EntityId) =>
    post<TriggerEvalJobResult>(`/v1/admin/eval-jobs/${id}/trigger`, {}),

  listRuns: (id: EntityId, limit = 50) =>
    get<EvalJobRunItem[]>(`/v1/admin/eval-jobs/${id}/runs`, {
      params: { limit },
    }),
};
