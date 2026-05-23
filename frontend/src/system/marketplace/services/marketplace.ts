import { get, post } from '@/core/lib/request';
import type { EntityId } from '@/core/types/api';
import type {
  AddRegistryPayload,
  InstallPayload,
  InstallResult,
  MarketplaceEntry,
  RegistryItem,
  SyncResult,
  UpdateRegistryPayload,
} from '@/system/marketplace/types/marketplace';

export const marketplaceApi = {
  listRegistries: () =>
    get<RegistryItem[]>('/v1/admin/marketplace/registries'),

  addRegistry: (p: AddRegistryPayload) =>
    post<RegistryItem>('/v1/admin/marketplace/registries', p),

  updateRegistry: (id: EntityId, p: UpdateRegistryPayload) =>
    post<RegistryItem>(
      `/v1/admin/marketplace/registries/${id}/update`,
      p,
    ),

  deleteRegistry: (id: EntityId) =>
    post<null>(`/v1/admin/marketplace/registries/${id}/delete`, {}),

  syncRegistry: (id: EntityId) =>
    post<SyncResult>(`/v1/admin/marketplace/registries/${id}/sync`, {}),

  search: (q: string, tag?: string) =>
    get<MarketplaceEntry[]>('/v1/admin/marketplace/search', {
      params: { q, tag },
    }),

  install: (p: InstallPayload) =>
    post<InstallResult>('/v1/admin/marketplace/install', p),
};
