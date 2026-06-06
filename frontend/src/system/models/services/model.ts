import { get, post } from '@/core/lib/request';
import { streamSSE } from '@/core/lib/sse';
import type { FlatSSEEvent } from '@/core/lib/sse-events';
import type { EntityId } from '@/core/types/api';
import type {
  CreateModelRequest,
  ModelCapabilities,
  ModelItem,
} from '@/system/models/types/model';

/** model test 的流事件 —— 在 FlatSSEEvent 基础上 narrow meta 字段 + 注明 end 扩展字段 */
export interface TestStreamChunk extends FlatSSEEvent {
  meta?: {
    kind: 'chat' | 'embedding' | 'rerank' | 'image' | 'video';
    model: string;
    provider: string;
  };
  /** 流末 end 携带 */
  latency_ms?: number;
  sample?: string;
  /** image 模型测试：生成完毕的产物图（final） */
  image_chunk?: { url: string; detail?: string; mime_type?: string };
  /** video 模型测试：生成完毕的产物视频 */
  video_chunk?: { url: string; detail?: string; mime_type?: string };
}

export const modelApi = {
  list: (params?: {
    kind?: 'chat' | 'embedding' | 'rerank' | 'image' | 'video';
    provider_id?: number;
  }) => get<ModelItem[]>('/v1/admin/models', { params }),
  create: (req: CreateModelRequest) => post<ModelItem>('/v1/admin/models', req),
  update: (
    id: EntityId,
    req: {
      provider_id?: EntityId;
      code?: string;
      dim?: number;
      defaults?: Record<string, unknown>;
      enabled?: boolean;
      upstream_name?: string;
      capabilities?: ModelCapabilities;
    },
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
      params?: Record<string, unknown>;
      inputImages?: string[];
      signal?: AbortSignal;
      onChunk: (chunk: TestStreamChunk) => void;
    },
  ): Promise<void> =>
    streamSSE<TestStreamChunk>(`/v1/admin/models/${id}/test/stream`, {
      body: {
        prompt: opts.prompt ?? null,
        params: opts.params ?? null,
        input_images: opts.inputImages ?? null,
      },
      signal: opts.signal,
      onChunk: opts.onChunk,
    }),
};
