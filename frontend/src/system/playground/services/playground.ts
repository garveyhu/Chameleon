/** Playground SSE 调用封装：薄一层，SSE 协议解析全部委托给 core/lib/sse */

import { streamSSE } from '@/core/lib/sse';
import type { InvokeChunk, InvokeRequest } from '@/system/playground/types/playground';

interface InvokeOptions {
  signal?: AbortSignal;
  onChunk: (chunk: InvokeChunk) => void;
}

export function streamInvoke(
  req: InvokeRequest,
  { signal, onChunk }: InvokeOptions,
): Promise<void> {
  return streamSSE<InvokeChunk>('/v1/admin/playground/invoke', {
    body: req,
    signal,
    onChunk,
  });
}
