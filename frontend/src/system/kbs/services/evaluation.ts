import { get, post } from '@/core/lib/request';
import type { PageResult } from '@/core/types/api';
import type {
  Evaluation,
  EvaluationListItem,
  CreateEvaluationRequest,
} from '@/system/kbs/types/evaluation';

export const evaluationApi = {
  create: (kbId: number, req: CreateEvaluationRequest) =>
    post<Evaluation>(`/v1/admin/kbs/${kbId}/evaluations`, req),

  list: (kbId: number, params?: { page?: number; page_size?: number }) =>
    get<PageResult<EvaluationListItem>>(
      `/v1/admin/kbs/${kbId}/evaluations`,
      { params },
    ),

  get: (kbId: number, evalId: number) =>
    get<Evaluation>(`/v1/admin/kbs/${kbId}/evaluations/${evalId}`),

  delete: (kbId: number, evalId: number) =>
    post<Evaluation>(
      `/v1/admin/kbs/${kbId}/evaluations/${evalId}/delete`,
      {},
    ),
};
