import type { EntityId } from '@/core/types/api';

export type PlaygroundRole = 'user' | 'assistant' | 'system';

export interface MessageAttachment {
  object_id: string;
  object_url: string;
  size: number;
  content_type: string | null;
  mime_kind: 'image' | 'audio' | 'pdf' | 'other';
}

/** P19.4 PR #42：ContentBlock 形态，对齐 OpenAI/Anthropic vision API */
export type ContentBlock =
  | { type: 'text'; text: string }
  | {
      type: 'image_url';
      image_url: { url: string; detail?: 'auto' | 'low' | 'high' };
    }
  | { type: 'audio_url'; audio_url: { url: string; format?: string } };

export interface PlaygroundMessage {
  id: string;
  role: PlaygroundRole;
  content: string;
  /** P19.4 PR #42：上传的多模态附件；user 消息发送时转 ContentBlock 列表 */
  attachments?: MessageAttachment[];
  /** UI 标记：流式中 / 完成 / 失败 */
  status?: 'streaming' | 'done' | 'failed';
  /** assistant 完成后填的 usage */
  usage?: PlaygroundUsage | null;
  error?: string | null;
  /** 后端 SSE meta 透出（assistant 才有），用于 feedback 上报 */
  requestId?: string;
  /** 用户当前的反馈：1=👍 / -1=👎 / null=未点 */
  feedback?: 1 | -1 | null;
  /** 该消息是否已被 edit/regenerate 替换（true 时灰显） */
  stale?: boolean;
}

export interface PlaygroundUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface PlaygroundParams {
  model_id?: EntityId;
  model_name?: string;
  system_prompt: string;
  temperature: number;
  top_p: number | null;
  max_tokens: number | null;
  kb_ids: EntityId[];
}

export interface InvokeRequest {
  model_id?: EntityId;
  model_name?: string;
  system_prompt?: string;
  temperature: number;
  top_p?: number | null;
  max_tokens?: number | null;
  messages: Array<{ role: PlaygroundRole; content: string | ContentBlock[] }>;
  kb_ids?: EntityId[];
}

export type InvokeChunk = import('@/core/lib/sse-events').FlatSSEEvent;
