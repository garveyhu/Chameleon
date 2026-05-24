/** chat store —— actions slice：列管理 + 消息级动作（send/edit/regenerate/...）
 *
 * 全部动作按 columnId 操作对应列的消息流。
 * AbortController 非序列化，存在模块级 Map，不入 store。
 */

import type { StateCreator } from 'zustand';

import { toast } from '@/core/lib/toast';
import {
  MAX_COLUMNS,
  newColumn,
  type ChatState,
} from '@/core/stores/chat/state';
import { scoreApi } from '@/system/call_logs/services/call-log';
import { toContentBlock } from '@/system/files/services/file-upload';
import type { UploadResult } from '@/system/files/services/file-upload';
import { streamInvoke } from '@/system/playground/services/playground';
import type {
  ContentBlock,
  InvokeChunk,
  MessageAttachment,
  PlaygroundMessage,
  PlaygroundParams,
} from '@/system/playground/types/playground';

export interface ChatActions {
  addColumn: () => void;
  removeColumn: (columnId: string) => void;
  updateParams: (columnId: string, params: PlaygroundParams) => void;
  send: (
    columnId: string,
    text: string,
    attachments: UploadResult[],
  ) => Promise<void>;
  stop: (columnId: string) => void;
  clearMessages: (columnId: string) => void;
  deleteMessage: (columnId: string, msgId: string) => void;
  editMessage: (columnId: string, msgId: string, next: string) => Promise<void>;
  regenerate: (columnId: string, msgId: string) => Promise<void>;
  translate: (columnId: string, msgId: string, lang?: string) => Promise<void>;
  continueGen: (columnId: string, msgId: string) => Promise<void>;
  setFeedback: (columnId: string, msgId: string, value: 1 | -1 | null) => void;
  setPinned: (columnId: string, msgId: string, next: boolean) => void;
}

export type ChatStore = ChatState & ChatActions;

/** 每列的进行中流控制器（非序列化，故不入 store） */
const aborters = new Map<string, AbortController>();

const newMsgId = (): string =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

/** history 消息 → 请求体 messages（含 attachments 的 user 转 ContentBlock 列表） */
function toReqMessages(history: PlaygroundMessage[]) {
  return history.map(m => {
    if (m.role === 'user' && m.attachments && m.attachments.length > 0) {
      const blocks: ContentBlock[] = [];
      if (m.content.trim()) blocks.push({ type: 'text', text: m.content });
      for (const a of m.attachments) {
        blocks.push(
          toContentBlock({ ...a, mime_kind: a.mime_kind }) as ContentBlock,
        );
      }
      return { role: m.role, content: blocks };
    }
    return { role: m.role, content: m.content };
  });
}

export const createChatActions: StateCreator<
  ChatStore,
  [['zustand/devtools', never]],
  [],
  ChatActions
> = (set, get) => {
  /** 整列消息替换 */
  const setMsgs = (
    columnId: string,
    updater: (prev: PlaygroundMessage[]) => PlaygroundMessage[],
    label: string,
  ) =>
    set(
      s => ({
        messages: {
          ...s.messages,
          [columnId]: updater(s.messages[columnId] ?? []),
        },
      }),
      false,
      label,
    );

  /** 单条消息 patch */
  const patch = (
    columnId: string,
    msgId: string,
    p: Partial<PlaygroundMessage>,
  ) =>
    setMsgs(
      columnId,
      prev => prev.map(m => (m.id === msgId ? { ...m, ...p } : m)),
      'chat/patchMessage',
    );

  const paramsOf = (columnId: string): PlaygroundParams | undefined =>
    get().columns.find(c => c.id === columnId)?.params;

  const requireModel = (params: PlaygroundParams | undefined): boolean => {
    if (!params?.model_id) {
      toast.error('请先选择模型');
      return false;
    }
    return true;
  };

  /** 核心流式调用：deltas 流进 columnId / targetId */
  const runInvoke = async (
    columnId: string,
    reqMessages: ReturnType<typeof toReqMessages>,
    targetId: string,
    overrides?: { system_prompt?: string },
  ) => {
    const params = paramsOf(columnId);
    if (!params) return;
    const controller = new AbortController();
    aborters.set(columnId, controller);
    try {
      await streamInvoke(
        {
          model_id: params.model_id,
          system_prompt:
            overrides?.system_prompt ?? params.system_prompt ?? undefined,
          temperature: params.temperature,
          top_p: params.top_p,
          max_tokens: params.max_tokens,
          messages: reqMessages,
          kb_ids: params.kb_ids.length ? params.kb_ids : undefined,
        },
        {
          signal: controller.signal,
          onChunk: (chunk: InvokeChunk) => {
            if (chunk.error) {
              patch(columnId, targetId, {
                status: 'failed',
                error: `${chunk.error.type}: ${chunk.error.message}`,
              });
              return;
            }
            if (chunk.meta && typeof chunk.meta.request_id === 'string') {
              patch(columnId, targetId, { requestId: chunk.meta.request_id });
            }
            if (chunk.delta) {
              setMsgs(
                columnId,
                prev =>
                  prev.map(m =>
                    m.id === targetId
                      ? { ...m, content: m.content + chunk.delta }
                      : m,
                  ),
                'chat/appendDelta',
              );
            }
            if (chunk.end) {
              patch(columnId, targetId, {
                status: 'done',
                usage: chunk.usage ?? null,
              });
            }
          },
        },
      );
    } catch (e) {
      const aborted = (e as DOMException)?.name === 'AbortError';
      patch(columnId, targetId, {
        status: 'failed',
        error: aborted ? '已中止' : String(e),
      });
    } finally {
      aborters.delete(columnId);
    }
  };

  return {
    addColumn: () => {
      if (get().columns.length >= MAX_COLUMNS) {
        toast.warning(`最多 ${MAX_COLUMNS} 列`);
        return;
      }
      const col = newColumn();
      set(
        s => ({
          columns: [...s.columns, col],
          messages: { ...s.messages, [col.id]: [] },
        }),
        false,
        'chat/addColumn',
      );
    },

    removeColumn: columnId => {
      aborters.get(columnId)?.abort();
      aborters.delete(columnId);
      set(
        s => {
          const { [columnId]: _drop, ...rest } = s.messages;
          void _drop;
          return {
            columns: s.columns.filter(c => c.id !== columnId),
            messages: rest,
          };
        },
        false,
        'chat/removeColumn',
      );
    },

    updateParams: (columnId, params) =>
      set(
        s => ({
          columns: s.columns.map(c =>
            c.id === columnId ? { ...c, params } : c,
          ),
        }),
        false,
        'chat/updateParams',
      ),

    send: async (columnId, text, attachments) => {
      const params = paramsOf(columnId);
      if (!requireModel(params)) return;
      const userAttachments: MessageAttachment[] | undefined =
        attachments.length > 0
          ? attachments.map(a => ({
              object_id: a.object_id,
              object_url: a.object_url,
              size: a.size,
              content_type: a.content_type,
              mime_kind: a.mime_kind,
            }))
          : undefined;
      const userMsg: PlaygroundMessage = {
        id: newMsgId(),
        role: 'user',
        content: text,
        attachments: userAttachments,
      };
      const aiMsg: PlaygroundMessage = {
        id: newMsgId(),
        role: 'assistant',
        content: '',
        status: 'streaming',
      };
      const history = [...(get().messages[columnId] ?? []), userMsg];
      setMsgs(columnId, prev => [...prev, userMsg, aiMsg], 'chat/send');
      await runInvoke(columnId, toReqMessages(history), aiMsg.id);
    },

    stop: columnId => aborters.get(columnId)?.abort(),

    clearMessages: columnId => {
      aborters.get(columnId)?.abort();
      setMsgs(columnId, () => [], 'chat/clearMessages');
    },

    deleteMessage: (columnId, msgId) =>
      setMsgs(
        columnId,
        prev => {
          const idx = prev.findIndex(m => m.id === msgId);
          if (idx < 0) return prev;
          const target = prev[idx];
          if (
            target.role === 'user' &&
            idx + 1 < prev.length &&
            prev[idx + 1].role === 'assistant'
          ) {
            return prev.filter((_, i) => i !== idx && i !== idx + 1);
          }
          return prev.filter((_, i) => i !== idx);
        },
        'chat/deleteMessage',
      ),

    editMessage: async (columnId, msgId, nextContent) => {
      const params = paramsOf(columnId);
      if (!requireModel(params)) return;
      const msgs = get().messages[columnId] ?? [];
      const idx = msgs.findIndex(m => m.id === msgId);
      if (idx < 0 || msgs[idx].role !== 'user') return;

      const replacedUser: PlaygroundMessage = {
        ...msgs[idx],
        content: nextContent,
      };
      const newAssistant: PlaygroundMessage = {
        id: newMsgId(),
        role: 'assistant',
        content: '',
        status: 'streaming',
      };
      const oldAssistant =
        idx + 1 < msgs.length && msgs[idx + 1].role === 'assistant'
          ? msgs[idx + 1]
          : null;
      setMsgs(
        columnId,
        () => [
          ...msgs.slice(0, idx),
          replacedUser,
          ...(oldAssistant ? [{ ...oldAssistant, stale: true }] : []),
          newAssistant,
        ],
        'chat/editMessage',
      );
      const history = [
        ...msgs.slice(0, idx).filter(m => !m.stale),
        replacedUser,
      ];
      await runInvoke(columnId, toReqMessages(history), newAssistant.id);
    },

    regenerate: async (columnId, msgId) => {
      const params = paramsOf(columnId);
      if (!requireModel(params)) return;
      const msgs = get().messages[columnId] ?? [];
      const idx = msgs.findIndex(m => m.id === msgId);
      if (idx < 0 || msgs[idx].role !== 'assistant') return;
      let userIdx = idx - 1;
      while (userIdx >= 0 && msgs[userIdx].role !== 'user') userIdx--;
      if (userIdx < 0) {
        toast.error('找不到对应的 user 消息');
        return;
      }
      const newAssistant: PlaygroundMessage = {
        id: newMsgId(),
        role: 'assistant',
        content: '',
        status: 'streaming',
      };
      setMsgs(
        columnId,
        () => [
          ...msgs.slice(0, idx),
          { ...msgs[idx], stale: true },
          newAssistant,
        ],
        'chat/regenerate',
      );
      const history = msgs.slice(0, idx).filter(m => !m.stale);
      await runInvoke(columnId, toReqMessages(history), newAssistant.id);
    },

    translate: async (columnId, msgId, lang) => {
      const params = paramsOf(columnId);
      if (!requireModel(params)) return;
      const msgs = get().messages[columnId] ?? [];
      const idx = msgs.findIndex(m => m.id === msgId);
      if (idx < 0 || !msgs[idx].content.trim()) return;
      const target = lang ?? 'English';
      const out: PlaygroundMessage = {
        id: newMsgId(),
        role: 'assistant',
        content: '',
        status: 'streaming',
      };
      setMsgs(
        columnId,
        prev => [...prev.slice(0, idx + 1), out, ...prev.slice(idx + 1)],
        'chat/translate',
      );
      await runInvoke(
        columnId,
        [{ role: 'user', content: msgs[idx].content }],
        out.id,
        {
          system_prompt: `你是专业翻译引擎。把用户内容翻译成 ${target}，只输出译文，不要解释。`,
        },
      );
    },

    continueGen: async (columnId, msgId) => {
      const params = paramsOf(columnId);
      if (!requireModel(params)) return;
      const msgs = get().messages[columnId] ?? [];
      const idx = msgs.findIndex(m => m.id === msgId);
      if (idx < 0 || msgs[idx].role !== 'assistant') return;
      patch(columnId, msgId, { status: 'streaming' });
      const history = msgs.slice(0, idx + 1).filter(m => !m.stale);
      const req = toReqMessages(history);
      req.push({ role: 'user', content: '请接着上面的内容继续写完，不要重复。' });
      await runInvoke(columnId, req, msgId);
    },

    setFeedback: (columnId, msgId, value) => {
      patch(columnId, msgId, { feedback: value });
      const msg = (get().messages[columnId] ?? []).find(m => m.id === msgId);
      if (value !== null && msg?.requestId) {
        void scoreApi
          .create({
            call_log_id: msg.requestId,
            trace_id: msg.requestId,
            name: 'thumbs',
            value,
            data_type: 'numeric',
            source: 'annotation',
          })
          .catch(() => toast.error('反馈写入失败'));
      }
    },

    setPinned: (columnId, msgId, next) =>
      patch(columnId, msgId, { pinned: next }),
  };
};
