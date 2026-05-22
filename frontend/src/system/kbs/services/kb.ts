import { get, post } from '@/core/lib/request';
import type { EntityId, PageResult } from '@/core/types/api';
import type {
  ChunkItem,
  KbChunkStrategy,
  KbItem,
} from '@/system/kbs/types/kb';

export interface UpdateKbAdminRequest {
  name?: string;
  description?: string;
  chunk_strategy?: KbChunkStrategy;
  default_top_k?: number;
  recall_mode?: 'vector' | 'hybrid' | 'keyword';
}

export const kbApi = {
  list: (params?: { page?: number; page_size?: number }) =>
    get<PageResult<KbItem>>('/v1/admin/kbs', { params }),
  get: (id: EntityId) => get<KbItem>(`/v1/admin/kbs/${id}`),
  update: (id: EntityId, req: UpdateKbAdminRequest) =>
    post<KbItem>(`/v1/admin/kbs/${id}/update`, req),
  listChunks: (id: EntityId, params?: { page?: number; page_size?: number }) =>
    get<PageResult<ChunkItem>>(`/v1/admin/kbs/${id}/chunks`, { params }),
};
