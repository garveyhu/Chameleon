import type { EntityId } from '@/core/types/api';
import { get, post } from '@/core/lib/request';
import type { PageResult } from '@/core/types/api';
import type {
  ApiKeyCreated,
  ApiKeyItem,
  AppItem,
  CreateApiKeyRequest,
  CreateAppRequest,
} from '@/system/apps/types/app';

export const appApi = {
  list: (params?: { page?: number; page_size?: number }) =>
    get<PageResult<AppItem>>('/v1/admin/apps', { params }),
  get: (id: EntityId) => get<AppItem>(`/v1/admin/apps/${id}`),
  create: (req: CreateAppRequest) => post<AppItem>('/v1/admin/apps', req),
  update: (id: EntityId, req: Partial<CreateAppRequest> & { status?: 'active' | 'suspended' }) =>
    post<AppItem>(`/v1/admin/apps/${id}/update`, req),
  delete: (id: EntityId) => post<void>(`/v1/admin/apps/${id}/delete`),
  listApiKeys: (id: EntityId) => get<ApiKeyItem[]>(`/v1/admin/apps/${id}/api-keys`),
  grantAgent: (id: EntityId, agent_key: string) =>
    post<void>(`/v1/admin/apps/${id}/agents/grant`, { agent_key }),
  revokeAgent: (id: EntityId, agent_key: string) =>
    post<void>(`/v1/admin/apps/${id}/agents/revoke`, { agent_key }),
  listAgents: (id: EntityId) => get<string[]>(`/v1/admin/apps/${id}/agents`),
};

export const apiKeyApi = {
  create: (req: CreateApiKeyRequest) => post<ApiKeyCreated>('/v1/admin/api-keys', req),
  revoke: (id: EntityId) => post<ApiKeyItem>(`/v1/admin/api-keys/${id}/revoke`),
};
