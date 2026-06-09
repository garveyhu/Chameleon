/** chat store —— actions slice：列管理 + 消息级动作（send/edit/regenerate/...）
 *
 * 全部动作按 columnId 操作对应列的消息流。
 * AbortController 非序列化，存在模块级 Map，不入 store。
 */

import type { StateCreator } from 'zustand';

import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import {
  MAX_COLUMNS,
  newColumn,
  newColumnId,
  newParams,
  persistChat,
  type ChatMode,
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
import { fillTemplate } from '@/system/playground/utils/template-vars';

export interface ChatActions {
  setApiKeyId: (apiKeyId: EntityId | null) => void;
  /** 切单聊 / 对比（持久化） */
  setMode: (mode: ChatMode) => void;
  addColumn: () => void;
  /** 新增一列并直接载入某历史会话（P3「单聊会话加入对比」） */
  addColumnLoaded: (
    sessionId: string,
    messages: PlaygroundMessage[],
    params?: Partial<PlaygroundParams>,
  ) => void;
  /** 把某列「提升」为单聊：只留该列 + 切单聊模式（P3） */
  promoteToSingle: (columnId: string) => void;
  removeColumn: (columnId: string) => void;
  // ── 对比历史（P2，客户端分组持久化）──
  /** 把当前对比工作区 upsert 进 compareHistory；modelLabels: columnId→模型名 */
  upsertActiveCompare: (modelLabels: Record<string, string>) => void;
  /** 开新对比：重置成单列空白、activeCompareId=null（保留历史） */
  newCompare: () => void;
  /** 打开历史对比：用快照重建列；返回需懒加载消息的 [columnId, sessionId][] */
  openCompare: (groupId: string) => Array<readonly [string, string]>;
  deleteCompare: (groupId: string) => void;
  updateParams: (columnId: string, params: PlaygroundParams) => void;
  send: (
    columnId: string,
    text: string,
    attachments: UploadResult[],
  ) => Promise<void>;
  /** durable HITL：回填人工答案，续跑暂停的 run（durable agent ctx.ask_human）*/
  resumeHuman: (columnId: string, msgId: string, answer: string) => Promise<void>;
  stop: (columnId: string) => void;
  clearMessages: (columnId: string) => void;
  /** 载入一条历史会话到列（设消息流 + 续接 sessionId + 可选恢复配置） */
  loadSession: (
    columnId: string,
    sessionId: string,
    messages: PlaygroundMessage[],
    params?: Partial<PlaygroundParams>,
  ) => void;
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

  /** 把可持久化切片写 localStorage（仅在非流式 mutation 后调，避开 delta 高频写） */
  const save = () => persistChat(get());

  /** 写回某列的溯源 sessionId（后端首条 invoke 经 meta 透出后续接用） */
  const setColumnSession = (columnId: string, sessionId: string) => {
    set(
      s => ({
        columns: s.columns.map(c =>
          c.id === columnId ? { ...c, sessionId } : c,
        ),
      }),
      false,
      'chat/setColumnSession',
    );
    save(); // 续接 id 落本地，reload 后能继续这轮会话
  };

  const requireModel = (params: PlaygroundParams | undefined): boolean => {
    if (!params?.model_id) {
      toast.error('请先选择模型');
      return false;
    }
    if (get().apiKeyId == null) {
      toast.error('请先选择一个溯源 Key');
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
    resume?: { runId: string; answer: string },
  ) => {
    const params = paramsOf(columnId);
    if (!params) return;
    // transient override（翻译等）走原文不模板化；正常发送把 {{var}} 替换成填值，
    // 未填的保留原占位符。仅改请求体，不动 params.system_prompt 原文（模板需留存）。
    const effectiveSystem: string | undefined =
      overrides?.system_prompt ??
      fillTemplate(params.system_prompt ?? '', params.var_values ?? {});
    const controller = new AbortController();
    aborters.set(columnId, controller);
    // durable HITL：本轮是否收到过 pending（暂停）。后端 pending 后仍会 emit end，end 不可把
    // paused 冲成 done，否则回填框秒消失（评审22 C1）。
    let sawPending = false;
    try {
      await streamInvoke(
        {
          api_key_id: get().apiKeyId,
          session_id: get().columns.find(c => c.id === columnId)?.sessionId,
          bound_agent_key: params.bound_agent_key,
          invoke_agent_key: params.invoke_agent_key,
          gen_params: params.invoke_agent_key ? params.gen_params : undefined,
          input_images: params.invoke_agent_key ? params.input_images : undefined,
          model_id: params.invoke_agent_key ? undefined : params.model_id,
          system_prompt: effectiveSystem,
          temperature: params.temperature,
          top_p: params.top_p,
          max_tokens: params.max_tokens,
          messages: reqMessages,
          kb_ids: params.kb_ids.length ? params.kb_ids : undefined,
          // transient override（如翻译临时 system_prompt）不写入会话配置快照
          persist_config: !overrides?.system_prompt,
          // durable HITL 续跑：回填答案到暂停的 run（后端用 pending 原始 query 重放）
          resume_run_id: resume?.runId,
          resume_answer: resume?.answer,
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
            if (chunk.meta && typeof chunk.meta.session_id === 'string') {
              setColumnSession(columnId, chunk.meta.session_id);
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
            if (chunk.pending) {
              // durable agent 暂停等人工输入 → 标 paused + 存 pending，UI 渲染回填框
              sawPending = true;
              patch(columnId, targetId, {
                status: 'paused',
                pending: {
                  prompt: chunk.pending.prompt,
                  runId: chunk.pending.run_id ?? '',
                  callIndex: chunk.pending.call_index ?? null,
                },
              });
            }
            if (chunk.end && !sawPending) {
              // 暂停态不被 end 冲成 done（否则回填框秒消失，评审22 C1）；resume 续跑时新一轮
              // runInvoke 的 end 才置 done。
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
    setApiKeyId: apiKeyId => {
      set({ apiKeyId }, false, 'chat/setApiKeyId');
      save();
    },

    setMode: mode => {
      set({ mode }, false, 'chat/setMode');
      save();
    },

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
      save();
    },

    addColumnLoaded: (sessionId, messages, params) => {
      if (get().columns.length >= MAX_COLUMNS) {
        toast.warning(`最多 ${MAX_COLUMNS} 列`);
        return;
      }
      const col = {
        id: newColumnId(),
        params: { ...newParams(), ...params },
        sessionId,
      };
      set(
        s => ({
          columns: [...s.columns, col],
          messages: { ...s.messages, [col.id]: messages },
        }),
        false,
        'chat/addColumnLoaded',
      );
      save();
    },

    promoteToSingle: columnId => {
      const col = get().columns.find(c => c.id === columnId);
      if (!col) return;
      const msgs = get().messages[columnId] ?? [];
      set(
        { mode: 'single', columns: [col], messages: { [columnId]: msgs }, activeCompareId: null },
        false,
        'chat/promoteToSingle',
      );
      save();
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
      save();
    },

    updateParams: (columnId, params) => {
      set(
        s => ({
          columns: s.columns.map(c =>
            c.id === columnId ? { ...c, params } : c,
          ),
        }),
        false,
        'chat/updateParams',
      );
      save();
    },

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

    /** durable HITL：回填人工答案，续跑暂停的 run（复用同 assistant 消息接续输出） */
    resumeHuman: async (columnId, msgId, answer) => {
      const msg = (get().messages[columnId] ?? []).find(m => m.id === msgId);
      const runId = msg?.pending?.runId;
      if (!runId) return;
      // 回 streaming + 清 pending；续跑结果（complete 重放 + ask 后产出）接入同消息
      patch(columnId, msgId, { status: 'streaming', pending: null, content: '', error: null });
      const answerMsg: PlaygroundMessage = { id: newMsgId(), role: 'user', content: answer };
      await runInvoke(columnId, toReqMessages([answerMsg]), msgId, undefined, { runId, answer });
    },

    stop: columnId => aborters.get(columnId)?.abort(),

    clearMessages: columnId => {
      aborters.get(columnId)?.abort();
      setMsgs(columnId, () => [], 'chat/clearMessages');
      // 清空消息 = 开新会话：重置该列 sessionId，下一条 invoke 会建新会话
      set(
        s => ({
          columns: s.columns.map(c =>
            c.id === columnId ? { ...c, sessionId: null } : c,
          ),
        }),
        false,
        'chat/clearMessages:resetSession',
      );
      save();
    },

    loadSession: (columnId, sessionId, messages, params) => {
      aborters.get(columnId)?.abort();
      set(
        s => ({
          columns: s.columns.map(c =>
            c.id === columnId
              ? {
                  ...c,
                  sessionId,
                  // 恢复会话当初的配置（model/KB/参数/关联应用）；缺省保留现状
                  params: params ? { ...c.params, ...params } : c.params,
                }
              : c,
          ),
          messages: { ...s.messages, [columnId]: messages },
        }),
        false,
        'chat/loadSession',
      );
      save();
    },

    upsertActiveCompare: modelLabels => {
      const st = get();
      const cols = st.columns.map(c => ({
        params: c.params,
        sessionId: c.sessionId ?? null,
        modelLabel: modelLabels[c.id],
      }));
      // 还没真正发过（无任何会话）不存，避免堆一堆空白对比
      if (!cols.some(c => c.sessionId)) return;
      const firstUser = (st.messages[st.columns[0]?.id] ?? []).find(
        m => m.role === 'user',
      );
      const label =
        firstUser?.content?.trim().slice(0, 30) ||
        cols
          .map(c => c.modelLabel)
          .filter(Boolean)
          .join(' vs ') ||
        '未命名对比';
      set(
        s => {
          const id = s.activeCompareId ?? newColumnId();
          const entry = { id, label, updatedAt: Date.now(), columns: cols };
          return {
            compareHistory: [
              entry,
              ...s.compareHistory.filter(g => g.id !== id),
            ],
            activeCompareId: id,
          };
        },
        false,
        'chat/upsertActiveCompare',
      );
      save();
    },

    newCompare: () => {
      const a = newColumn();
      const b = newColumn();
      set(
        {
          columns: [a, b],
          messages: { [a.id]: [], [b.id]: [] },
          activeCompareId: null,
        },
        false,
        'chat/newCompare',
      );
      save();
    },

    openCompare: groupId => {
      const g = get().compareHistory.find(x => x.id === groupId);
      if (!g) return [];
      const cols = g.columns.map(c => ({
        id: newColumnId(),
        params: c.params,
        sessionId: c.sessionId,
      }));
      set(
        { columns: cols, messages: {}, activeCompareId: g.id, mode: 'compare' },
        false,
        'chat/openCompare',
      );
      save();
      return cols
        .filter(c => c.sessionId)
        .map(c => [c.id, c.sessionId as string] as const);
    },

    deleteCompare: groupId => {
      set(
        s => ({
          compareHistory: s.compareHistory.filter(g => g.id !== groupId),
          activeCompareId:
            s.activeCompareId === groupId ? null : s.activeCompareId,
        }),
        false,
        'chat/deleteCompare',
      );
      save();
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
