/** session_token 管理：首次创建 + 过期自动重签 */

import type { EmbedApi } from './api';
import { EmbedError } from './api';
import type { StreamChunk } from './types';

interface SessionState {
  token: string;
  expiresAt: number; // 毫秒
}

const isTokenInvalidError = (e: unknown): boolean =>
  e instanceof EmbedError && (e.code === 401 || e.code === 4030 || e.code === 4040 || e.code === 40113);

export class SessionManager {
  private api: EmbedApi;
  private state: SessionState | null = null;

  constructor(api: EmbedApi) {
    this.api = api;
  }

  async getToken(): Promise<string> {
    if (this.state && Date.now() < this.state.expiresAt - 30_000) {
      return this.state.token;
    }
    const res = await this.api.createSession();
    this.state = {
      token: res.session_token,
      expiresAt: Date.now() + res.expires_in * 1000,
    };
    return this.state.token;
  }

  async refresh(): Promise<string> {
    this.state = null;
    return this.getToken();
  }

  async invokeWithRetry(input: string): Promise<{ answer: string; session_id: string }> {
    const token = await this.getToken();
    try {
      return await this.api.invoke(token, input);
    } catch (e) {
      if (isTokenInvalidError(e)) {
        const newToken = await this.refresh();
        return this.api.invoke(newToken, input);
      }
      throw e;
    }
  }

  async streamWithRetry(
    input: string,
    onChunk: (c: StreamChunk) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    const token = await this.getToken();
    try {
      await this.api.invokeStream(token, input, onChunk, signal);
    } catch (e) {
      if (isTokenInvalidError(e)) {
        const newToken = await this.refresh();
        await this.api.invokeStream(newToken, input, onChunk, signal);
        return;
      }
      throw e;
    }
  }
}
