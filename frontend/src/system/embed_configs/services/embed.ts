import type { EntityId } from '@/core/types/api';
import { get, post } from '@/core/lib/request';
import type { PageResult } from '@/core/types/api';
import type {
  CreateEmbedConfigRequest,
  EmbedConfigItem,
} from '@/system/embed_configs/types/embed';

export const embedConfigApi = {
  list: (params?: { page?: number; page_size?: number }) =>
    get<PageResult<EmbedConfigItem>>('/v1/admin/embed-configs', { params }),
  create: (req: CreateEmbedConfigRequest) =>
    post<EmbedConfigItem>('/v1/admin/embed-configs', req),
  update: (id: EntityId, req: Partial<CreateEmbedConfigRequest> & { enabled?: boolean }) =>
    post<EmbedConfigItem>(`/v1/admin/embed-configs/${id}/update`, req),
  delete: (id: EntityId) => post<void>(`/v1/admin/embed-configs/${id}/delete`),
};
