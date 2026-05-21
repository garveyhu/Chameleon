/** session_token 管理：首次创建 + 过期自动重签 */

import type { EmbedApi } from './api';
import { EmbedError } from './api';

interface SessionState {
  token: string;
  expiresAt: number; // 毫秒
}

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

  /** session_token 与 embed_key 不匹配（后端 401）→ 重签后调用方应重试 */
  async refresh(): Promise<string> {
    this.state = null;
    return this.getToken();
  }

  async invokeWithRetry(input: string): Promise<{ answer: string; session_id: string }> {
    const token = await this.getToken();
    try {
      return await this.api.invoke(token, input);
    } catch (e) {
      if (e instanceof EmbedError && (e.code === 401 || e.code === 4030 || e.code === 4040)) {
        const newToken = await this.refresh();
        return this.api.invoke(newToken, input);
      }
      throw e;
    }
  }
}
