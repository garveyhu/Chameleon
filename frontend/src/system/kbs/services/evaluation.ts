import { get, post } from '@/core/lib/request';
import type { EntityId, PageResult } from '@/core/types/api';
import type {
  CreateEvaluationRequest,
  Evaluation,
  EvaluationListItem,
} from '@/system/kbs/types/evaluation';

export const evaluationApi = {
  create: (kbId: EntityId, req: CreateEvaluationRequest) =>
    post<Evaluation>(`/v1/admin/kbs/${kbId}/evaluations`, req),

  list: (kbId: EntityId, params?: { page?: number; page_size?: number }) =>
    get<PageResult<EvaluationListItem>>(
      `/v1/admin/kbs/${kbId}/evaluations`,
      { params },
    ),

  get: (kbId: EntityId, evalId: EntityId) =>
    get<Evaluation>(`/v1/admin/kbs/${kbId}/evaluations/${evalId}`),

  delete: (kbId: EntityId, evalId: EntityId) =>
    post<Evaluation>(
      `/v1/admin/kbs/${kbId}/evaluations/${evalId}/delete`,
      {},
    ),
};
