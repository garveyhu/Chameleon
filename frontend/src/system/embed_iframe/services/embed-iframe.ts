/** iframe 嵌入接口客户端（公开 API，不带 Authorization） */

import type {
  IframeCreateSessionResp,
  IframeInvokeResp,
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

  invoke: (
    embedKey: string,
    sessionToken: string,
    input: string,
  ): Promise<IframeInvokeResp> =>
    call(`/v1/embed/${embedKey}/invoke`, {
      method: 'POST',
      body: JSON.stringify({ session_token: sessionToken, input }),
    }),
};
