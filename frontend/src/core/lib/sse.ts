/** SSE 客户端通用工具
 *
 * 设计：
 * - 后端用 `chameleon.core.api.sse.sse_response` 统一封装，每条 chunk 一行 `data: {...JSON}\n\n`，
 *   流末附 `data: [DONE]\n\n`
 * - 前端只需提供 `onChunk(chunk)` 回调；网络/HTTP 错误抛 Error，业务错误由 chunk.error 表达
 * - 鉴权 token 自动从 storage 取，挂 Authorization header
 *
 * 用法：
 *   await streamSSE<MyChunk>('/v1/...', {
 *     body: { foo: 1 },
 *     signal: ctrl.signal,
 *     onChunk: ch => { ... },
 *   });
 */

import { STORAGE_KEY } from '@/core/constants/app';

const DONE_MARKER = '[DONE]';

export interface StreamSSEOptions<T> {
  /** 请求 body，自动 JSON.stringify。不传则不发 body。 */
  body?: unknown;
  /** HTTP method，默认 POST。 */
  method?: 'POST' | 'GET' | 'PUT';
  /** 额外 headers（覆盖默认）。 */
  headers?: Record<string, string>;
  /** 中断信号。 */
  signal?: AbortSignal;
  /** 每收到一个业务 chunk 调一次。 */
  onChunk: (chunk: T) => void;
}

/** 发起 SSE 请求并按行解析。返回 promise resolves 在流自然结束或 [DONE]。 */
export async function streamSSE<T>(url: string, opts: StreamSSEOptions<T>): Promise<void> {
  const token = localStorage.getItem(STORAGE_KEY.ACCESS_TOKEN);
  const method = opts.method ?? 'POST';
  const init: RequestInit = {
    method,
    signal: opts.signal,
    headers: {
      Accept: 'text/event-stream',
      ...(opts.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...opts.headers,
    },
  };
  if (opts.body !== undefined && method !== 'GET') {
    init.body = JSON.stringify(opts.body);
  }

  const resp = await fetch(url, init);
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`SSE HTTP ${resp.status}：${text.slice(0, 200)}`);
  }
  if (!resp.body) {
    throw new Error('SSE 响应无 body');
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let done = false;

  const flushBlock = (block: string): boolean => {
    for (const line of block.split('\n')) {
      if (!line.startsWith('data:')) continue;
      const payload = line.slice(5).trim();
      if (!payload) continue;
      if (payload === DONE_MARKER) {
        return true;
      }
      try {
        opts.onChunk(JSON.parse(payload) as T);
      } catch {
        // 非 JSON 行（可能是心跳）忽略
      }
    }
    return false;
  };

  while (!done) {
    const { done: readerDone, value } = await reader.read();
    if (readerDone) break;
    buffer += decoder.decode(value, { stream: true });
    let idx = buffer.indexOf('\n\n');
    while (idx !== -1) {
      if (flushBlock(buffer.slice(0, idx))) {
        done = true;
        break;
      }
      buffer = buffer.slice(idx + 2);
      idx = buffer.indexOf('\n\n');
    }
  }
  // 残块（少数 server 不发末尾 \n\n）
  if (!done && buffer.length > 0) {
    flushBlock(buffer);
  }
}
