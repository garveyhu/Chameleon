import { get, post } from '@/core/lib/request';
import type { PageResult } from '@/core/types/api';
import type { ChunkItem, KbItem } from '@/system/kbs/types/kb';

export const kbApi = {
  list: (params?: { page?: number; page_size?: number }) =>
    get<PageResult<KbItem>>('/v1/admin/kbs', { params }),
  get: (id: number) => get<KbItem>(`/v1/admin/kbs/${id}`),
  update: (id: number, req: { name?: string; description?: string }) =>
    post<KbItem>(`/v1/admin/kbs/${id}/update`, req),
  listChunks: (id: number, params?: { page?: number; page_size?: number }) =>
    get<PageResult<ChunkItem>>(`/v1/admin/kbs/${id}/chunks`, { params }),
};
