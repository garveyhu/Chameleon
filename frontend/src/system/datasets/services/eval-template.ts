import { get, post } from '@/core/lib/request';
import type { EntityId } from '@/core/types/api';
import type {
  CreateEvalTemplateRequest,
  EvalTemplateItem,
  ScoreDistributionResult,
  UpdateEvalTemplateRequest,
} from '@/system/datasets/types/eval-template';

export const evalTemplateApi = {
  list: () => get<EvalTemplateItem[]>('/v1/admin/eval-templates'),
  get: (id: EntityId) =>
    get<EvalTemplateItem>(`/v1/admin/eval-templates/${id}`),
  create: (req: CreateEvalTemplateRequest) =>
    post<EvalTemplateItem>('/v1/admin/eval-templates', req),
  update: (id: EntityId, req: UpdateEvalTemplateRequest) =>
    post<EvalTemplateItem>(
      `/v1/admin/eval-templates/${id}/update`,
      req,
    ),
  delete: (id: EntityId) =>
    post<void>(`/v1/admin/eval-templates/${id}/delete`),

  scoreDistribution: (
    runId: EntityId,
    params?: { threshold?: number; buckets?: number },
  ) =>
    get<ScoreDistributionResult>(
      `/v1/admin/datasets/runs/${runId}/score-distribution`,
      { params },
    ),
};
