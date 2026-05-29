/** chat store —— state slice：状态形态 + 初始值 + 工厂
 *
 * playground 多列调试的全局状态，按 columnId 分键。
 * messages 与 columns 分开存：columns 持参数，messages 持每列消息流。
 */

import type { EntityId } from '@/core/types/api';
import type {
  PlaygroundMessage,
  PlaygroundParams,
} from '@/system/playground/types/playground';

/** 并排列上限 */
export const MAX_COLUMNS = 4;

export interface ChatColumn {
  id: string;
  params: PlaygroundParams;
  /** 溯源会话 id（后端首条 invoke 经 meta 透出，后续轮续接；清空消息时重置） */
  sessionId?: string | null;
}

export interface ChatState {
  /** 并排列（顺序即渲染顺序） */
  columns: ChatColumn[];
  /** 每列消息流，key = columnId */
  messages: Record<string, PlaygroundMessage[]>;
  /** 全局绑定的 owner key（系统理念：模型随便用，但流量必须挂 key 溯源） */
  apiKeyId: EntityId | null;
}

export const newColumnId = (): string =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `col-${Date.now()}-${Math.random().toString(16).slice(2)}`;

export const newParams = (): PlaygroundParams => ({
  system_prompt: '',
  temperature: 0.7,
  top_p: 1,
  max_tokens: null,
  kb_ids: [],
});

export const newColumn = (): ChatColumn => ({
  id: newColumnId(),
  params: newParams(),
});

export function createInitialState(): ChatState {
  const first = newColumn();
  return {
    columns: [first],
    messages: { [first.id]: [] },
    apiKeyId: null,
  };
}
