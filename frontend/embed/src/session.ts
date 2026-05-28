/** session_token 管理：首次创建 + 过期自动重签 + localStorage 持久化 device_id（匿名身份） */

import type { EmbedApi } from './api';
import { EmbedError } from './api';
import type { InvokeResponse, StreamChunk, WidgetAttachment } from './types';

interface SessionState {
  token: string;
  expiresAt: number; // 毫秒
}

const isTokenInvalidError = (e: unknown): boolean =>
  e instanceof EmbedError && (e.code === 401 || e.code === 4030 || e.code === 4040 || e.code === 40113);

/** S12：在 localStorage 拿 / 生成一个稳定的 device_id（匿名身份模式用）
 *
 * key 用 embed_key 隔离 —— 同浏览器多个嵌入应用各有独立 device_id；
 * crypto.randomUUID 不可用时回退 Date.now+random 凑。
 */
const deviceIdFor = (embedKey: string): string => {
  const key = `chameleon-embed:device:${embedKey}`;
  try {
    const existing = localStorage.getItem(key);
    if (existing) return existing;
  } catch {
    // localStorage 不可用（cookie 禁、SSR、iframe sandbox）→ 用临时随机；不持久
    return generateRandomDeviceId();
  }
  const fresh = generateRandomDeviceId();
  try {
    localStorage.setItem(key, fresh);
  } catch {
    /* 忽略 */
  }
  return fresh;
};

const generateRandomDeviceId = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `dev_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
};

export interface SessionManagerOptions {
  /** 接入方传入的外部用户 id（external_user_id 模式） */
  externalUserId?: string;
  /** 接入方签名的 JWT（signed_jwt 模式） */
  jwtToken?: string;
}

export class SessionManager {
  private api: EmbedApi;
  private embedKey: string;
  private opts: SessionManagerOptions;
  private state: SessionState | null = null;

  constructor(api: EmbedApi, embedKey: string, opts: SessionManagerOptions = {}) {
    this.api = api;
    this.embedKey = embedKey;
    this.opts = opts;
  }

  /** 按场景拼装身份字段 —— 接入方传外部 id / JWT 优先；否则 anonymous_device */
  private resolveIdentity(): {
    device_id?: string;
    external_user_id?: string;
    jwt_token?: string;
  } {
    if (this.opts.jwtToken) {
      return { jwt_token: this.opts.jwtToken };
    }
    if (this.opts.externalUserId) {
      return { external_user_id: this.opts.externalUserId };
    }
    return { device_id: deviceIdFor(this.embedKey) };
  }

  async getToken(): Promise<string> {
    if (this.state && Date.now() < this.state.expiresAt - 30_000) {
      return this.state.token;
    }
    const res = await this.api.createSession(this.resolveIdentity());
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

  async invokeWithRetry(
    input: string,
    attachments?: WidgetAttachment[],
  ): Promise<InvokeResponse> {
    const token = await this.getToken();
    try {
      return await this.api.invoke(token, input, attachments);
    } catch (e) {
      if (isTokenInvalidError(e)) {
        const newToken = await this.refresh();
        return this.api.invoke(newToken, input, attachments);
      }
      throw e;
    }
  }

  async streamWithRetry(
    input: string,
    onChunk: (c: StreamChunk) => void,
    signal?: AbortSignal,
    attachments?: WidgetAttachment[],
  ): Promise<void> {
    const token = await this.getToken();
    try {
      await this.api.invokeStream(token, input, onChunk, signal, attachments);
    } catch (e) {
      if (isTokenInvalidError(e)) {
        const newToken = await this.refresh();
        await this.api.invokeStream(newToken, input, onChunk, signal, attachments);
        return;
      }
      throw e;
    }
  }
}
