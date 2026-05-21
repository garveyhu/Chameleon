/** widget 与后端 /v1/embed/* 的契约客户端 */

import type {
  ApiResult,
  CreateSessionResponse,
  EmbedPublicConfig,
  InvokeResponse,
} from './types';

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

  async createSession(): Promise<CreateSessionResponse> {
    return this.unwrap(
      await fetch(`${this.apiBase}/v1/embed/${this.embedKey}/session`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
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
