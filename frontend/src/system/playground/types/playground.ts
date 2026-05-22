import type { EntityId } from '@/core/types/api';

export type PlaygroundRole = 'user' | 'assistant' | 'system';

export interface PlaygroundMessage {
  id: string;
  role: PlaygroundRole;
  content: string;
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
  messages: Array<{ role: PlaygroundRole; content: string }>;
  kb_ids?: EntityId[];
}

export type InvokeChunk = import('@/core/lib/sse-events').FlatSSEEvent;
