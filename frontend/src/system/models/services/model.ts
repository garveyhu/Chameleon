import { get, post } from '@/core/lib/request';
import type { CreateModelRequest, ModelItem } from '@/system/models/types/model';

export const modelApi = {
  list: (params?: { kind?: 'chat' | 'embedding'; provider_id?: number }) =>
    get<ModelItem[]>('/v1/admin/models', { params }),
  create: (req: CreateModelRequest) => post<ModelItem>('/v1/admin/models', req),
  update: (
    id: number,
    req: { dim?: number; defaults?: Record<string, unknown>; enabled?: boolean },
  ) => post<ModelItem>(`/v1/admin/models/${id}/update`, req),
  delete: (id: number) => post<void>(`/v1/admin/models/${id}/delete`),
  test: (id: number) =>
    post<{ ok: boolean; latency_ms: number; sample: string; detail: string }>(
      `/v1/admin/models/${id}/test`,
    ),
};
