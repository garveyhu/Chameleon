import { get, post } from '@/core/lib/request';
import type { EntityId } from '@/core/types/api';
import type {
  AppTemplateItem,
  CreateAppTemplateRequest,
  InstallTemplateResult,
} from '@/system/marketplace/types/template';

export const appTemplateApi = {
  list: (params?: {
    only_verified?: boolean;
    category?: string;
    limit?: number;
  }) =>
    get<AppTemplateItem[]>('/v1/admin/app-templates', { params }),
  get: (id: EntityId) =>
    get<AppTemplateItem>(`/v1/admin/app-templates/${id}`),
  create: (req: CreateAppTemplateRequest) =>
    post<AppTemplateItem>('/v1/admin/app-templates', req),
  verify: (id: EntityId, verified: boolean) =>
    post<AppTemplateItem>(`/v1/admin/app-templates/${id}/verify`, {
      verified,
    }),
  install: (id: EntityId) =>
    post<InstallTemplateResult>(`/v1/admin/app-templates/${id}/install`),
  delete: (id: EntityId) =>
    post<void>(`/v1/admin/app-templates/${id}/delete`),
};
