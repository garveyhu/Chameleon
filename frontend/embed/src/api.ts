/** widget 与后端 /v1/embed/* 的契约客户端 */

import type {
  ApiResult,
  CreateSessionResponse,
  EmbedPublicConfig,
  InvokeResponse,
  StreamChunk,
} from './types';

const DONE_MARKER = '[DONE]';

export class EmbedApi {
  private apiBase: string;
  private embedKey: string;

  constructor(apiBase: string, embedKey: string) {
    this.apiBase = apiBase.replace(/\/$/, '');
    this.embedKey = embedKey;
  }

  async getConfig(): Promise<EmbedPublicConfig> {
    return this.unwrap(
      await fetch(`${this.apiBase}/v1/embed/${this.embedKey}/config`, {
        method: 'GET',
        headers: { 'content-type': 'application/json' },
      })
    );
  }

  /** 颁 session_token；按 embed 的 session_policy.identification_mode 传不同身份字段 */
  async createSession(identity?: {
    device_id?: string;
    external_user_id?: string;
    jwt_token?: string;
  }): Promise<CreateSessionResponse> {
    return this.unwrap(
      await fetch(`${this.apiBase}/v1/embed/${this.embedKey}/session`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: identity ? JSON.stringify(identity) : undefined,
      })
    );
  }

  async invoke(sessionToken: string, input: string): Promise<InvokeResponse> {
    return this.unwrap(
      await fetch(`${this.apiBase}/v1/embed/${this.embedKey}/invoke`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ session_token: sessionToken, input }),
      })
    );
  }

  /** 反馈：write-only，不接 ApiResult，失败仅 console.warn（不打断会话） */
  async feedback(payload: {
    trace_id: string;
    name: string;
    value?: number;
    string_value?: string;
    comment?: string;
  }): Promise<void> {
    try {
      await fetch(`${this.apiBase}/v1/embed/${this.embedKey}/feedback`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
    } catch (err) {
      console.warn('[ChameleonWidget] feedback POST failed', err);
    }
  }

  async invokeStream(
    sessionToken: string,
    input: string,
    onChunk: (chunk: StreamChunk) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    const resp = await fetch(`${this.apiBase}/v1/embed/${this.embedKey}/invoke/stream`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        accept: 'text/event-stream',
      },
      body: JSON.stringify({ session_token: sessionToken, input }),
      signal,
    });
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new EmbedError(resp.status, `HTTP ${resp.status}: ${text.slice(0, 200)}`);
    }
    if (!resp.body) {
      throw new EmbedError(resp.status, 'SSE 响应无 body');
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let done = false;
    const flush = (block: string): boolean => {
      for (const line of block.split('\n')) {
        if (!line.startsWith('data:')) continue;
        const payload = line.slice(5).trim();
        if (!payload) continue;
        if (payload === DONE_MARKER) return true;
        try {
          onChunk(JSON.parse(payload) as StreamChunk);
        } catch {
          /* 忽略非 JSON 行 */
        }
      }
      return false;
    };
    while (!done) {
      const { done: rd, value } = await reader.read();
      if (rd) break;
      buffer += decoder.decode(value, { stream: true });
      let idx = buffer.indexOf('\n\n');
      while (idx !== -1) {
        if (flush(buffer.slice(0, idx))) {
          done = true;
          break;
        }
        buffer = buffer.slice(idx + 2);
        idx = buffer.indexOf('\n\n');
      }
    }
    if (!done && buffer.length > 0) flush(buffer);
  }

  private async unwrap<T>(res: Response): Promise<T> {
    let body: ApiResult<T> | null = null;
    try {
      body = (await res.json()) as ApiResult<T>;
    } catch {
      throw new EmbedError(res.status, `HTTP ${res.status}: 响应非 JSON`);
    }
    if (!res.ok || body.success === false) {
      throw new EmbedError(body.code || res.status, body.message || 'unknown error');
    }
    return body.data;
  }
}

export class EmbedError extends Error {
  code: number;
  constructor(code: number, message: string) {
    super(message);
    this.code = code;
    this.name = 'EmbedError';
  }
}
