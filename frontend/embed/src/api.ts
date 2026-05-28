/** widget 与后端 /v1/embed/* 的契约客户端 */

import type {
  ApiResult,
  CreateNewSessionResponse,
  CreateSessionResponse,
  EmbedMessageItem,
  EmbedPublicConfig,
  EmbedSessionItem,
  InvokeResponse,
  StreamChunk,
  WidgetAttachment,
} from './types';

/** invoke 请求时只下发后端要的最小字段（kind 是 widget 本地分类，不发） */
const toWireAttachment = (a: WidgetAttachment) => ({
  object_url: a.object_url,
  filename: a.filename,
  mime: a.mime,
  size: a.size,
});

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

  // ── S11/S12B：会话管理 ────────────────────────────────────────

  /** 列出当前 token 绑的 end_user 的历史会话（按 last_message_at 倒序） */
  async listSessions(sessionToken: string): Promise<EmbedSessionItem[]> {
    const url = `${this.apiBase}/v1/embed/${this.embedKey}/sessions?session_token=${encodeURIComponent(sessionToken)}`;
    return this.unwrap(await fetch(url, { method: 'GET' }));
  }

  /** 切到某历史会话，加载其消息列表（按 seq 正序） */
  async listMessages(sessionToken: string, sessionId: string): Promise<EmbedMessageItem[]> {
    const url = `${this.apiBase}/v1/embed/${this.embedKey}/sessions/${encodeURIComponent(sessionId)}/messages?session_token=${encodeURIComponent(sessionToken)}`;
    return this.unwrap(await fetch(url, { method: 'GET' }));
  }

  /** 显式开新对话 —— 同 token 切到新 sid，不刷新页面 */
  async createNewSession(sessionToken: string): Promise<CreateNewSessionResponse> {
    return this.unwrap(
      await fetch(`${this.apiBase}/v1/embed/${this.embedKey}/sessions/new`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ session_token: sessionToken }),
      }),
    );
  }

  /** end-user 软删自己的会话；受 session_policy.allow_user_manage */
  async deleteSession(sessionToken: string, sessionId: string): Promise<void> {
    await this.unwrap(
      await fetch(
        `${this.apiBase}/v1/embed/${this.embedKey}/sessions/${encodeURIComponent(sessionId)}/delete`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ session_token: sessionToken }),
        },
      ),
    );
  }

  /** end-user 重命名自己的会话；受 session_policy.allow_user_manage */
  async renameSession(
    sessionToken: string,
    sessionId: string,
    title: string,
  ): Promise<EmbedSessionItem> {
    return this.unwrap(
      await fetch(
        `${this.apiBase}/v1/embed/${this.embedKey}/sessions/${encodeURIComponent(sessionId)}/name`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ session_token: sessionToken, title }),
        },
      ),
    );
  }

  async invoke(
    sessionToken: string,
    input: string,
    attachments?: WidgetAttachment[],
  ): Promise<InvokeResponse> {
    const body: Record<string, unknown> = { session_token: sessionToken, input };
    if (attachments && attachments.length) {
      body.attachments = attachments.map(toWireAttachment);
    }
    return this.unwrap(
      await fetch(`${this.apiBase}/v1/embed/${this.embedKey}/invoke`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
      })
    );
  }

  /** 回复后建议追问（基于刚才一轮 Q/A 让 LLM 生成 3 个 follow-up） */
  async suggestFollowups(
    sessionToken: string,
    question: string,
    answer: string,
  ): Promise<string[]> {
    return this.unwrap(
      await fetch(`${this.apiBase}/v1/embed/${this.embedKey}/suggest-followups`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ session_token: sessionToken, question, answer }),
      }),
    );
  }

  /** 三步上传到 MinIO：presign → PUT → finalize（返回 long-lived object_url） */
  async uploadFile(file: File, sessionToken: string): Promise<WidgetAttachment> {
    // 浏览器对 .md / .svg / .epub 经常给空 file.type → 按扩展名兜底
    const effectiveMime = normalizeMime(file.name, file.type);
    // 1. presign —— 走 embed 路由（origin + session_token 鉴权，无需 API Key）
    const presign = (await this.unwrap(
      await fetch(
        `${this.apiBase}/v1/embed/${this.embedKey}/files/presigned-upload`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            session_token: sessionToken,
            filename: file.name,
            content_type: effectiveMime,
            size: file.size,
          }),
        },
      ),
    )) as { object_id: string; upload_url: string; object_url: string };
    // 2. PUT MinIO（不带 Authorization；MinIO presigned 自验签）
    const putResp = await fetch(presign.upload_url, {
      method: 'PUT',
      headers: { 'content-type': effectiveMime },
      body: file,
    });
    if (!putResp.ok) {
      throw new EmbedError(putResp.status, `直传 MinIO 失败: ${putResp.status}`);
    }
    // 3. finalize —— 同样走 embed 路由
    const fin = (await this.unwrap(
      await fetch(
        `${this.apiBase}/v1/embed/${this.embedKey}/files/${encodeURIComponent(presign.object_id)}/finalize`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ session_token: sessionToken }),
        },
      ),
    )) as { object_url: string; content_type: string | null };
    const mime = fin.content_type || file.type || 'application/octet-stream';
    return {
      object_url: fin.object_url,
      filename: file.name,
      mime,
      size: file.size,
      kind: classifyKind(mime),
    };
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
    attachments?: WidgetAttachment[],
  ): Promise<void> {
    const body: Record<string, unknown> = { session_token: sessionToken, input };
    if (attachments && attachments.length) {
      body.attachments = attachments.map(toWireAttachment);
    }
    const resp = await fetch(`${this.apiBase}/v1/embed/${this.embedKey}/invoke/stream`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        accept: 'text/event-stream',
      },
      body: JSON.stringify(body),
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

/** 浏览器对 .md / .svg / .epub 经常给空 mime —— 按扩展名兜底 */
const EXT_TO_MIME: Record<string, string> = {
  md: 'text/markdown',
  markdown: 'text/markdown',
  mdx: 'text/markdown',
  txt: 'text/plain',
  log: 'text/plain',
  csv: 'text/csv',
  html: 'text/html',
  htm: 'text/html',
  xml: 'application/xml',
  json: 'application/json',
  pdf: 'application/pdf',
  doc: 'application/msword',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xls: 'application/vnd.ms-excel',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  ppt: 'application/vnd.ms-powerpoint',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  epub: 'application/epub+zip',
  rtf: 'application/rtf',
  zip: 'application/zip',
  eml: 'message/rfc822',
  msg: 'application/vnd.ms-outlook',
  svg: 'image/svg+xml',
};

export const normalizeMime = (filename: string, mime: string): string => {
  const m = (mime || '').toLowerCase();
  if (m && m !== 'application/octet-stream') return m;
  const ext = filename.includes('.') ? filename.split('.').pop()!.toLowerCase() : '';
  return EXT_TO_MIME[ext] || m || 'application/octet-stream';
};

/** 把 MIME 分到 widget 用的 kind 标签 */
const classifyKind = (mime: string): WidgetAttachment['kind'] => {
  const m = mime.toLowerCase();
  if (m.startsWith('image/')) return 'image';
  if (m.startsWith('audio/')) return 'audio';
  // 文档族（含 Markdown / TXT / HTML / PDF / Word / PPT / EPUB / RTF / XML / EML）
  if (
    m === 'application/pdf' ||
    m === 'application/msword' ||
    m === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
    m === 'application/vnd.ms-powerpoint' ||
    m === 'application/vnd.openxmlformats-officedocument.presentationml.presentation' ||
    m === 'application/epub+zip' ||
    m === 'application/rtf' ||
    m === 'application/xml' ||
    m === 'application/xhtml+xml' ||
    m === 'application/json' ||
    m === 'message/rfc822' ||
    m === 'application/vnd.ms-outlook' ||
    m.startsWith('text/')
  ) {
    return 'document';
  }
  // 数据表
  if (
    m === 'text/csv' ||
    m === 'application/csv' ||
    m === 'application/vnd.ms-excel' ||
    m === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  ) {
    return 'data';
  }
  return 'other';
};

export class EmbedError extends Error {
  code: number;
  constructor(code: number, message: string) {
    super(message);
    this.code = code;
    this.name = 'EmbedError';
  }
}
