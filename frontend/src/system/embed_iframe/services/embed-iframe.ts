/** iframe 嵌入接口客户端（公开 API，不带 Authorization） */
import { streamSSE } from '@/core/lib/sse';
import type {
  EmbedStreamChunk,
  IframeCreateSessionResp,
  IframePublicConfig,
} from '@/system/embed_iframe/types/embed-iframe';

interface Result<T> {
  code: number;
  message: string;
  data: T;
  success: boolean;
}

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers || {}) },
  });
  let body: Result<T>;
  try {
    body = (await res.json()) as Result<T>;
  } catch {
    throw new Error(`HTTP ${res.status}: 响应非 JSON`);
  }
  if (!res.ok || body.success === false) {
    throw new Error(body.message || `HTTP ${res.status}`);
  }
  return body.data;
}

export const embedIframeApi = {
  getConfig: (embedKey: string): Promise<IframePublicConfig> =>
    call(`/v1/embed/${embedKey}/config`),

  createSession: (embedKey: string): Promise<IframeCreateSessionResp> =>
    call(`/v1/embed/${embedKey}/session`, { method: 'POST' }),

  /** SSE 流式调用：边收 delta 边渲染。公开端点，streamSSE 在无 token 时不发 Authorization */
  streamInvoke: (
    embedKey: string,
    sessionToken: string,
    input: string,
    opts: { signal?: AbortSignal; onChunk: (chunk: EmbedStreamChunk) => void },
  ): Promise<void> =>
    streamSSE<EmbedStreamChunk>(`/v1/embed/${embedKey}/invoke/stream`, {
      body: { session_token: sessionToken, input },
      signal: opts.signal,
      onChunk: opts.onChunk,
    }),
};
