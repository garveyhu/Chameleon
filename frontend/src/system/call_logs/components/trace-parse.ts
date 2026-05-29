/** Trace payload 解析：纯函数，无 JSX。被 trace-payload(渲染) 与 trace-export(导出) 共用。 */

import { createContext } from 'react';

/** 导出图片时强制展开所有折叠区（截图要全量内容） */
export const ExportContext = createContext(false);

export type Payload = Record<string, unknown> | null | undefined;

/** 主文本字段优先级（generation 节点 prompt/answer 快照） */
export const INPUT_TEXT_KEYS = [
  'prompt_preview',
  'input',
  'question',
  'query',
  'text',
  'content',
];
export const OUTPUT_TEXT_KEYS = [
  'output_preview',
  'output',
  'answer',
  'text',
  'content',
];

export const pickText = (payload: Payload, keys: string[]): string | null => {
  if (!payload || typeof payload !== 'object') return null;
  for (const k of keys) {
    const v = (payload as Record<string, unknown>)[k];
    if (typeof v === 'string' && v.trim()) return v;
  }
  return null;
};

export interface RoleMsg {
  role: string;
  content: string;
}

export const ROLE_LABEL: Record<string, string> = {
  system: '系统',
  human: '用户',
  user: '用户',
  ai: '助手',
  assistant: '助手',
  tool: '工具',
  function: '工具',
};

export const ROLE_BAR: Record<string, string> = {
  system: 'bg-stone-400',
  human: 'bg-blue-500',
  user: 'bg-blue-500',
  ai: 'bg-violet-400',
  assistant: 'bg-violet-400',
  tool: 'bg-amber-400',
  function: 'bg-amber-400',
};

// prompt 快照 "[role] content"（角色间 \n 分隔，content 内部也可能含 \n）
const ROLE_RE = /(?=^\[(?:system|human|ai|user|assistant|tool|function)\][ \t]?)/im;

/** 解析 "[role] ..." 多消息文本；非该格式返 null */
export const parseMessages = (text: string): RoleMsg[] | null => {
  if (!/^\[(system|human|ai|user|assistant|tool|function)\]/i.test(text.trimStart()))
    return null;
  const parts = text.split(ROLE_RE).filter(p => p.trim());
  const msgs: RoleMsg[] = [];
  for (const p of parts) {
    const m = p.match(/^\[(\w+)\][ \t]?([\s\S]*)$/);
    if (m) msgs.push({ role: m[1].toLowerCase(), content: m[2].trim() });
  }
  return msgs.length ? msgs : null;
};

/** 从 payload 取消息流：优先结构化 messages（新格式），回退解析 prompt_preview（老行）。 */
export const extractMessages = (
  payload: Payload,
  textKeys: string[],
): RoleMsg[] | null => {
  if (payload && typeof payload === 'object') {
    const arr = (payload as Record<string, unknown>).messages;
    if (Array.isArray(arr)) {
      const msgs = arr
        .filter((m): m is Record<string, unknown> => !!m && typeof m === 'object')
        .map(m => ({
          role: typeof m.role === 'string' ? m.role.toLowerCase() : 'user',
          content: typeof m.content === 'string' ? m.content : String(m.content ?? ''),
        }));
      if (msgs.length) return msgs;
    }
  }
  const text = pickText(payload, textKeys);
  return text ? parseMessages(text) : null;
};

/** 结构化引用（retriever 节点输出 / KB 召回片段） */
export interface Citation {
  /** 来源标签（知识库名） */
  source: string;
  /** doc#seq 定位 */
  ref: string;
  content: string;
  /** 召回模式：vector / keyword / hybrid（决定分数语义） */
  mode?: string;
  /** 统一相关度分数（向量=相似度 / 关键词=BM25 / 混合=RRF） */
  score?: number;
  /** 命中子分数（按召回模式存在） */
  vector_score?: number;
  bm25_score?: number;
  rerank_score?: number;
}

/** 把消息流分组：系统 / 历史对话 / 本轮输入（最后一条 user 之前的对话为历史） */
export const groupInput = (
  messages: RoleMsg[],
): { system: RoleMsg[]; history: RoleMsg[]; current: RoleMsg | null } => {
  const system = messages.filter(m => m.role === 'system');
  const convo = messages.filter(m => m.role !== 'system');
  let curIdx = -1;
  for (let i = convo.length - 1; i >= 0; i--) {
    if (convo[i].role === 'user' || convo[i].role === 'human') {
      curIdx = i;
      break;
    }
  }
  if (curIdx < 0) {
    // 无 user（异常）→ 全当历史，无本轮
    return { system, history: convo, current: null };
  }
  return {
    system,
    history: convo.slice(0, curIdx),
    current: convo[curIdx],
  };
};
