import type { EntityId } from '@/core/types/api';

export interface ConversationItem {
  id: EntityId;
  session_id: string;
  agent_key: string;
  app_id: string;
  /** 终端用户外部 id（接入方传入；用于按用户筛 / 计费） */
  end_user_id: string | null;
  /** 该 session 绑的 owner key id（API/embed/openai 入口盖章；admin 为 NULL） */
  api_key_id: EntityId | null;
  provider_conv_id: string | null;
  title: string | null;
  meta: Record<string, unknown> | null;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface MessageItem {
  id: EntityId;
  session_id: string;
  seq: number;
  role: 'user' | 'assistant' | 'system' | 'tool' | string;
  content: string;
  content_blocks: Array<Record<string, unknown>> | null;
  steps: Array<Record<string, unknown>> | null;
  citations: Array<Record<string, unknown>> | null;
  tool_calls: Array<Record<string, unknown>> | null;
  usage: Record<string, unknown> | null;
  provider: string | null;
  parent_message_id: EntityId | null;
  /** 本条消息所属调用的 trace_id（= call_logs.request_id）；可下钻 trace */
  request_id: string | null;
  /** 用户对该消息的反馈：1 = 👍，-1 = 👎，null = 未反馈 */
  feedback: number | null;
  created_at: string;
}
