import { get, post } from '@/core/lib/request';
import type { PageResult } from '@/core/types/api';
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
  get: (id: number) => get<KbItem>(`/v1/admin/kbs/${id}`),
  update: (id: number, req: UpdateKbAdminRequest) =>
    post<KbItem>(`/v1/admin/kbs/${id}/update`, req),
  listChunks: (id: number, params?: { page?: number; page_size?: number }) =>
    get<PageResult<ChunkItem>>(`/v1/admin/kbs/${id}/chunks`, { params }),
};
