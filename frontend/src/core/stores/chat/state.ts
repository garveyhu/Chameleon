/** chat store —— state slice：状态形态 + 初始值 + 工厂 + 本地持久化
 *
 * playground 多列调试的全局状态，按 columnId 分键。
 * messages 与 columns 分开存：columns 持参数，messages 持每列消息流。
 *
 * 持久化（手写 localStorage，对齐 preferences/auth-store 风格）：
 * 只存 columns(id/params/sessionId) + mode + 对比历史 + apiKeyId，**不存 messages**
 * （reload 后按各列 sessionId 懒加载），避免把整段对话灌进 localStorage。
 */

import type { EntityId } from '@/core/types/api';
import type {
  PlaygroundMessage,
  PlaygroundParams,
} from '@/system/playground/types/playground';

/** 并排列上限 */
export const MAX_COLUMNS = 4;

export type ChatMode = 'single' | 'compare';

export interface ChatColumn {
  id: string;
  params: PlaygroundParams;
  /** 溯源会话 id（后端首条 invoke 经 meta 透出，后续轮续接；清空消息时重置） */
  sessionId?: string | null;
}

/** 一次「对比」= 一组并排列的快照（客户端分组，不依赖后端 group 字段）。
 *  打开时按各列 sessionId 重新拉消息还原。 */
export interface CompareColumnSnapshot {
  params: PlaygroundParams;
  sessionId: string | null;
  /** 列头展示的模型名（拉列表时已知，存下来免再查） */
  modelLabel?: string;
}

export interface CompareGroup {
  id: string;
  /** 列表展示名：取首条 user 内容 / 模型名拼接 */
  label: string;
  updatedAt: number;
  columns: CompareColumnSnapshot[];
}

export interface ChatState {
  /** 单聊 / 对比 两态（持久化，reload 回到原模式） */
  mode: ChatMode;
  /** 并排列（顺序即渲染顺序） */
  columns: ChatColumn[];
  /** 每列消息流，key = columnId（不持久化） */
  messages: Record<string, PlaygroundMessage[]>;
  /** 全局绑定的 owner key（系统理念：模型随便用，但流量必须挂 key 溯源） */
  apiKeyId: EntityId | null;
  /** 保存过的对比布局（对比模式历史侧栏的数据源） */
  compareHistory: CompareGroup[];
  /** 当前对比对应 compareHistory 里的哪条（null = 未保存的新对比） */
  activeCompareId: string | null;
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
  var_values: {},
});

export const newColumn = (): ChatColumn => ({
  id: newColumnId(),
  params: newParams(),
});

// ── 本地持久化 ──────────────────────────────────────────────

const PERSIST_KEY = 'chameleon:playground:chat:v1';

interface PersistedChat {
  mode: ChatMode;
  columns: ChatColumn[];
  apiKeyId: EntityId | null;
  compareHistory: CompareGroup[];
  activeCompareId: string | null;
}

/** 把可持久化切片写 localStorage（剔除 messages 等非序列化/大字段）。 */
export function persistChat(s: ChatState): void {
  try {
    const payload: PersistedChat = {
      mode: s.mode,
      columns: s.columns.map(c => ({
        id: c.id,
        params: c.params,
        sessionId: c.sessionId ?? null,
      })),
      apiKeyId: s.apiKeyId,
      compareHistory: s.compareHistory,
      activeCompareId: s.activeCompareId,
    };
    localStorage.setItem(PERSIST_KEY, JSON.stringify(payload));
  } catch {
    /* localStorage 不可用 / 配额满，忽略 */
  }
}

function loadPersisted(): PersistedChat | null {
  try {
    const raw = localStorage.getItem(PERSIST_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as PersistedChat;
    if (!Array.isArray(p.columns) || p.columns.length === 0) return null;
    return p;
  } catch {
    return null;
  }
}

export function createInitialState(): ChatState {
  const p = loadPersisted();
  if (p) {
    return {
      mode: p.mode === 'compare' ? 'compare' : 'single',
      columns: p.columns.map(c => ({
        id: c.id,
        params: c.params,
        sessionId: c.sessionId ?? null,
      })),
      messages: {}, // 挂载时按 sessionId 懒加载
      apiKeyId: p.apiKeyId ?? null,
      compareHistory: Array.isArray(p.compareHistory) ? p.compareHistory : [],
      activeCompareId: p.activeCompareId ?? null,
    };
  }
  const first = newColumn();
  return {
    mode: 'single',
    columns: [first],
    messages: { [first.id]: [] },
    apiKeyId: null,
    compareHistory: [],
    activeCompareId: null,
  };
}
