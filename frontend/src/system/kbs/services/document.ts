import { get, post, postForm } from '@/core/lib/request';
import type { PageResult } from '@/core/types/api';
import type {
  ChunkItem,
  DocumentItem,
  DocumentStatus,
  DocumentStatusInfo,
  IngestQueued,
  SearchHitItem,
  SearchRequest,
} from '@/system/kbs/types/kb';

export const documentApi = {
  list: (
    kbId: number,
    params?: {
      page?: number;
      page_size?: number;
      status?: DocumentStatus;
      tag?: string;
    },
  ) =>
    get<PageResult<DocumentItem>>(`/v1/admin/kbs/${kbId}/documents`, {
      params,
    }),

  get: (kbId: number, docId: number) =>
    get<DocumentItem>(`/v1/admin/kbs/${kbId}/documents/${docId}`),

  status: (kbId: number, docId: number) =>
    get<DocumentStatusInfo>(`/v1/admin/kbs/${kbId}/documents/${docId}/status`),

  upload: (kbId: number, files: File[]) => {
    const fd = new FormData();
    for (const f of files) fd.append('files', f, f.name);
    return postForm<IngestQueued[]>(
      `/v1/admin/kbs/${kbId}/documents/upload`,
      fd,
    );
  },

  fromUrl: (kbId: number, url: string, name?: string) =>
    post<IngestQueued>(`/v1/admin/kbs/${kbId}/documents/url`, { url, name }),

  fromText: (kbId: number, name: string, content: string) =>
    post<IngestQueued>(`/v1/admin/kbs/${kbId}/documents/text`, {
      name,
      content,
    }),

  delete: (kbId: number, docId: number) =>
    post<DocumentItem>(
      `/v1/admin/kbs/${kbId}/documents/${docId}/delete`,
      {},
    ),

  listChunks: (
    kbId: number,
    docId: number,
    params?: { page?: number; page_size?: number },
  ) =>
    get<PageResult<ChunkItem>>(
      `/v1/admin/kbs/${kbId}/documents/${docId}/chunks`,
      { params },
    ),

  search: (kbId: number, req: SearchRequest) =>
    post<SearchHitItem[]>(`/v1/admin/kbs/${kbId}/search`, req),
};
