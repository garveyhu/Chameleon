import type { EntityId } from '@/core/types/api';
import { get, post } from '@/core/lib/request';
import type { CreateProviderRequest, ProviderItem } from '@/system/providers/types/provider';

export const providerApi = {
  list: () => get<ProviderItem[]>('/v1/admin/providers'),
  create: (req: CreateProviderRequest) => post<ProviderItem>('/v1/admin/providers', req),
  update: (id: EntityId, req: Partial<CreateProviderRequest> & { enabled?: boolean }) =>
    post<ProviderItem>(`/v1/admin/providers/${id}/update`, req),
  delete: (id: EntityId) => post<void>(`/v1/admin/providers/${id}/delete`),
};
