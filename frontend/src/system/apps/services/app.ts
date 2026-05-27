import type { EntityId, PageResult } from '@/core/types/api';
import { get, post } from '@/core/lib/request';
import type {
  ApiKeyCreated,
  ApiKeyItem,
  CreateApiKeyRequest,
} from '@/system/apps/types/app';

export const apiKeyApi = {
  list: (params?: { page?: number; page_size?: number; include_revoked?: boolean }) =>
    get<PageResult<ApiKeyItem>>('/v1/admin/api-keys', { params }),
  create: (req: CreateApiKeyRequest) => post<ApiKeyCreated>('/v1/admin/api-keys', req),
  revoke: (id: EntityId) => post<ApiKeyItem>(`/v1/admin/api-keys/${id}/revoke`),
};
