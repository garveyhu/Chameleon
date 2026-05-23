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

export interface ChunkingPreviewPayload {
  text: string;
  strategy: KbChunkStrategy;
}

export interface ChunkingPreviewItem {
  seq: number;
  content: string;
  char_count: number;
  token_count_approx: number;
}

export interface ChunkingPreviewResult {
  mode: string;
  count: number;
  chunks: ChunkingPreviewItem[];
}

export const kbApi = {
  list: (params?: { page?: number; page_size?: number }) =>
    get<PageResult<KbItem>>('/v1/admin/kbs', { params }),
  get: (id: EntityId) => get<KbItem>(`/v1/admin/kbs/${id}`),
  update: (id: EntityId, req: UpdateKbAdminRequest) =>
    post<KbItem>(`/v1/admin/kbs/${id}/update`, req),
  listChunks: (id: EntityId, params?: { page?: number; page_size?: number }) =>
    get<PageResult<ChunkItem>>(`/v1/admin/kbs/${id}/chunks`, { params }),
  /** P18.4 实时预览（不写库） */
  chunkingPreview: (payload: ChunkingPreviewPayload) =>
    post<ChunkingPreviewResult>('/v1/admin/kbs/chunking-preview', payload),
};
