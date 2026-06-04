/** Playground SSE 调用封装：薄一层，SSE 协议解析全部委托给 core/lib/sse */

import { post } from '@/core/lib/request';
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

export interface RewritePromptRequest {
  current_prompt: string;
  answer: string;
  instruction: string;
  model_code?: string | null;
}

export interface RewritePromptResponse {
  rewritten_prompt: string;
}

/** 基于一条模型回答即时改写 System Prompt（非流式，结果直接回灌 ParamPanel）。 */
export function rewritePrompt(
  req: RewritePromptRequest,
): Promise<RewritePromptResponse> {
  return post<RewritePromptResponse>('/v1/admin/playground/prompt/rewrite', req);
}
