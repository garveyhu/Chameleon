import { get, post } from '@/core/lib/request';
import { streamSSE } from '@/core/lib/sse';
import type { EntityId } from '@/core/types/api';
import type { CreateModelRequest, ModelItem } from '@/system/models/types/model';

export interface TestStreamChunk {
  meta?: {
    kind: 'chat' | 'embedding';
    model: string;
    provider: string;
  };
  delta?: string;
  end?: boolean;
  latency_ms?: number;
  usage?: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  } | null;
  sample?: string;
  error?: {
    type: string;
    message: string;
  };
}

export const modelApi = {
  list: (params?: { kind?: 'chat' | 'embedding'; provider_id?: number }) =>
    get<ModelItem[]>('/v1/admin/models', { params }),
  create: (req: CreateModelRequest) => post<ModelItem>('/v1/admin/models', req),
  update: (
    id: EntityId,
    req: { dim?: number; defaults?: Record<string, unknown>; enabled?: boolean },
  ) => post<ModelItem>(`/v1/admin/models/${id}/update`, req),
  delete: (id: EntityId) => post<void>(`/v1/admin/models/${id}/delete`),
  test: (id: EntityId) =>
    post<{ ok: boolean; latency_ms: number; sample: string; detail: string }>(
      `/v1/admin/models/${id}/test`,
    ),
  /** SSE 流式测试：onChunk 逐 chunk 回调，throw 异常 = 网络/HTTP 级失败。
   *  业务级错误（provider 报错等）由 chunk.error 表达，不 throw。 */
  streamTest: (
    id: EntityId,
    opts: {
      prompt?: string;
      signal?: AbortSignal;
      onChunk: (chunk: TestStreamChunk) => void;
    },
  ): Promise<void> =>
    streamSSE<TestStreamChunk>(`/v1/admin/models/${id}/test/stream`, {
      body: { prompt: opts.prompt ?? null },
      signal: opts.signal,
      onChunk: opts.onChunk,
    }),
};
