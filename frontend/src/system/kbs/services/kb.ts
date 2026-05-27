import { get, post } from '@/core/lib/request';
import type { EntityId, PageResult } from '@/core/types/api';
import type {
  ChunkItem,
  KbApiKey,
  KbChunkStrategy,
  KbItem,
} from '@/system/kbs/types/kb';

export interface CreateKbRequest {
  kb_key: string;
  name: string;
  description?: string;
  embedding_model?: string;
  chunk_size?: number;
  chunk_overlap?: number;
  chunk_strategy?: KbChunkStrategy;
}

export interface UpdateKbAdminRequest {
  name?: string;
  description?: string;
  /** 自定义图标：base64 data URL；传空串清除 */
  icon?: string;
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
  create: (req: CreateKbRequest) => post<KbItem>('/v1/admin/kbs', req),
  get: (id: EntityId) => get<KbItem>(`/v1/admin/kbs/${id}`),
  update: (id: EntityId, req: UpdateKbAdminRequest) =>
    post<KbItem>(`/v1/admin/kbs/${id}/update`, req),
  delete: (id: EntityId) => post<null>(`/v1/admin/kbs/${id}/delete`, {}),
  // KB 作用域 API 密钥（kbs- 前缀）
  listKeys: (id: EntityId) => get<KbApiKey[]>(`/v1/admin/kbs/${id}/api-keys`),
  createKey: (id: EntityId, name: string) =>
    post<KbApiKey>(`/v1/admin/kbs/${id}/api-keys`, { name }),
  revokeKey: (id: EntityId, keyId: EntityId) =>
    post<KbApiKey>(`/v1/admin/kbs/${id}/api-keys/${keyId}/revoke`, {}),
  listChunks: (id: EntityId, params?: { page?: number; page_size?: number }) =>
    get<PageResult<ChunkItem>>(`/v1/admin/kbs/${id}/chunks`, { params }),
  /** P18.4 实时预览（不写库） */
  chunkingPreview: (payload: ChunkingPreviewPayload) =>
    post<ChunkingPreviewResult>('/v1/admin/kbs/chunking-preview', payload),
};
