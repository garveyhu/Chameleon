import type { EntityId } from '@/core/types/api';

export interface ConversationItem {
  id: EntityId;
  session_id: string;
  agent_key: string;
  app_id: string;
  title: string | null;
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
  created_at: string;
}

/** 树形节点：一条消息 + 其所有 children（按 seq 升序） */
export interface MessageTreeNode {
  message: MessageItem;
  children: MessageTreeNode[];
}

/** 树形渲染的"线性视图"单元：每条消息 + 兄弟分支信息 */
export interface BranchRenderItem {
  message: MessageItem;
  /** 同 parent 下的兄弟分支总数（1 = 没分支） */
  siblingCount: number;
  /** 当前在第几个分支（1-based，便于显示 "2/3"） */
  siblingIndex: number;
  /** 同 parent 下所有兄弟的 message id（用于切换器） */
  siblingIds: EntityId[];
}
