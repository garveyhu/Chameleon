import { get, post } from '@/core/lib/request';
import type { EntityId, PageResult } from '@/core/types/api';
import type {
  CreateEvalTemplateRequest,
  EvalTemplateItem,
  ScoreDistributionResult,
  TemplateUsageCount,
  UpdateEvalTemplateRequest,
} from '@/system/datasets/types/eval-template';

export const evalTemplateApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    keyword?: string;
    sort_by?: string;
    order?: string;
  }) =>
    get<PageResult<EvalTemplateItem>>('/v1/admin/eval-templates', { params }),
  get: (id: EntityId) =>
    get<EvalTemplateItem>(`/v1/admin/eval-templates/${id}`),
  /** 该模板被多少定时评测任务引用（评分方案库「应用数」badge）。 */
  usageCount: (id: EntityId) =>
    get<TemplateUsageCount>(`/v1/admin/eval-templates/${id}/usage-count`),
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
