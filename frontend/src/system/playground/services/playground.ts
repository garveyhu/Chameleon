/** Playground SSE 调用封装
 *
 * fetch + ReadableStream 自实现 SSE 解析，吐回 chunk 流。
 * 走 `/core/lib/request` 拿不到 fetch stream，所以这里 fetch 直接走。
 * 鉴权 token 从 storage 读出来手工挂 Authorization header。
 */

import { STORAGE_KEY } from '@/core/constants/app';
import type { InvokeChunk, InvokeRequest } from '@/system/playground/types/playground';

interface InvokeOptions {
  signal?: AbortSignal;
  onChunk: (chunk: InvokeChunk) => void;
}

export async function streamInvoke(
  req: InvokeRequest,
  { signal, onChunk }: InvokeOptions,
): Promise<void> {
  const token = localStorage.getItem(STORAGE_KEY.ACCESS_TOKEN);
  const resp = await fetch('/v1/admin/playground/invoke', {
    method: 'POST',
    signal,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(
      `playground SSE 失败：HTTP ${resp.status} ${text.slice(0, 200)}`,
    );
  }
  if (!resp.body) {
    throw new Error('playground SSE 失败：response 无 body');
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE 以 \n\n 分包；data: 开头的行 payload 是 JSON
    let idx = buffer.indexOf('\n\n');
    while (idx !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      idx = buffer.indexOf('\n\n');
      const lines = block.split('\n');
      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        const payload = line.slice(5).trim();
        if (!payload) continue;
        try {
          const obj = JSON.parse(payload) as InvokeChunk;
          onChunk(obj);
        } catch {
          // 忽略非 JSON 行（兼容心跳）
        }
      }
    }
  }

  // 最后兜底处理尾部残块
  if (buffer.startsWith('data:')) {
    const payload = buffer.slice(5).trim();
    if (payload) {
      try {
        onChunk(JSON.parse(payload) as InvokeChunk);
      } catch {
        /* ignore */
      }
    }
  }
}
