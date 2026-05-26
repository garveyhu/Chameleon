import { get, post, postForm } from '@/core/lib/request';
import type { EntityId, PageResult } from '@/core/types/api';
import type {
  ChunkItem,
  DocumentItem,
  DocumentStatus,
  DocumentStatusInfo,
  IngestQueued,
  KbChunkStrategy,
  SearchHitItem,
  SearchRequest,
} from '@/system/kbs/types/kb';

export type BatchAction = 'enable' | 'disable' | 'delete' | 'reindex';

export interface BatchResult {
  action: BatchAction;
  affected: number;
  queued: IngestQueued[];
}

export const documentApi = {
  list: (
    kbId: EntityId,
    params?: {
      page?: number;
      page_size?: number;
      status?: DocumentStatus;
      tag?: string;
      sort_by?: 'created_at' | 'token_count' | 'chunk_count';
      order?: 'asc' | 'desc';
    },
  ) =>
    get<PageResult<DocumentItem>>(`/v1/admin/kbs/${kbId}/documents`, {
      params,
    }),

  get: (kbId: EntityId, docId: EntityId) =>
    get<DocumentItem>(`/v1/admin/kbs/${kbId}/documents/${docId}`),

  status: (kbId: EntityId, docId: EntityId) =>
    get<DocumentStatusInfo>(`/v1/admin/kbs/${kbId}/documents/${docId}/status`),

  upload: (kbId: EntityId, files: File[]) => {
    const fd = new FormData();
    for (const f of files) fd.append('files', f, f.name);
    return postForm<IngestQueued[]>(`/v1/admin/kbs/${kbId}/documents/upload`, fd);
  },

  fromUrl: (kbId: EntityId, url: string, name?: string) =>
    post<IngestQueued>(`/v1/admin/kbs/${kbId}/documents/url`, { url, name }),

  fromText: (kbId: EntityId, name: string, content: string) =>
    post<IngestQueued>(`/v1/admin/kbs/${kbId}/documents/text`, {
      name,
      content,
    }),

  delete: (kbId: EntityId, docId: EntityId) =>
    post<DocumentItem>(`/v1/admin/kbs/${kbId}/documents/${docId}/delete`, {}),

  listChunks: (kbId: EntityId, docId: EntityId, params?: { page?: number; page_size?: number }) =>
    get<PageResult<ChunkItem>>(`/v1/admin/kbs/${kbId}/documents/${docId}/chunks`, { params }),

  /** 段落编辑（改内容重嵌 / 关键词 / 启停） */
  updateChunk: (
    kbId: EntityId,
    docId: EntityId,
    chunkId: EntityId,
    req: { content?: string; keywords?: string[]; enabled?: boolean },
  ) => post<ChunkItem>(`/v1/admin/kbs/${kbId}/documents/${docId}/chunks/${chunkId}/update`, req),

  deleteChunk: (kbId: EntityId, docId: EntityId, chunkId: EntityId) =>
    post<null>(`/v1/admin/kbs/${kbId}/documents/${docId}/chunks/${chunkId}/delete`, {}),

  search: (kbId: EntityId, req: SearchRequest) =>
    post<SearchHitItem[]>(`/v1/admin/kbs/${kbId}/search`, req),

  update: (
    kbId: EntityId,
    docId: EntityId,
    req: {
      tags?: string[];
      meta?: Record<string, unknown>;
      chunk_strategy?: KbChunkStrategy;
      enabled?: boolean;
    },
  ) => post<DocumentItem>(`/v1/admin/kbs/${kbId}/documents/${docId}/update`, req),

  /** 批量启停 / 删除 / 重建 */
  batch: (kbId: EntityId, action: BatchAction, docIds: EntityId[]) =>
    post<BatchResult>(`/v1/admin/kbs/${kbId}/documents/batch`, {
      action,
      doc_ids: docIds,
    }),

  reindex: (kbId: EntityId, docId: EntityId) =>
    post<IngestQueued>(`/v1/admin/kbs/${kbId}/documents/${docId}/reindex`, {}),

  reindexAll: (kbId: EntityId) => post<IngestQueued[]>(`/v1/admin/kbs/${kbId}/reindex-all`, {}),
};
