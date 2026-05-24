/** Playground 单列消息状态 + 全部消息级动作
 *
 * 从 chat-column 抽出：messages state + invoke 主流程 + send/edit/regenerate/
 * delete/translate/continueGen/feedback/pin。chat-column 退化为纯渲染 + 输入态。
 */

import { useCallback, useMemo, useRef, useState } from 'react';

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

const newId = () =>
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
        blocks.push(toContentBlock({ ...a, mime_kind: a.mime_kind }) as ContentBlock);
      }
      return { role: m.role, content: blocks };
    }
    return { role: m.role, content: m.content };
  });
}

export interface UsePlaygroundChat {
  messages: PlaygroundMessage[];
  streaming: boolean;
  send: (text: string, attachments: UploadResult[]) => Promise<void>;
  stop: () => void;
  clear: () => void;
  deleteMessage: (id: string) => void;
  editMessage: (id: string, next: string) => Promise<void>;
  regenerate: (id: string) => Promise<void>;
  translate: (id: string, lang?: string) => Promise<void>;
  continueGen: (id: string) => Promise<void>;
  setFeedback: (id: string, value: 1 | -1 | null) => void;
  setPinned: (id: string, next: boolean) => void;
}

export function usePlaygroundChat(
  params: PlaygroundParams,
  onError: (msg: string) => void,
): UsePlaygroundChat {
  const [messages, setMessages] = useState<PlaygroundMessage[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const streaming = useMemo(
    () => messages.some(m => m.status === 'streaming'),
    [messages],
  );

  const patch = useCallback(
    (id: string, p: Partial<PlaygroundMessage>) =>
      setMessages(prev => prev.map(m => (m.id === id ? { ...m, ...p } : m))),
    [],
  );

  /** 核心流式调用：把 deltas 流进 targetId 这条 assistant 消息 */
  const runInvoke = useCallback(
    async (
      reqMessages: ReturnType<typeof toReqMessages>,
      targetId: string,
      overrides?: { system_prompt?: string },
    ) => {
      const controller = new AbortController();
      abortRef.current = controller;
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
                patch(targetId, {
                  status: 'failed',
                  error: `${chunk.error.type}: ${chunk.error.message}`,
                });
                return;
              }
              if (chunk.meta && typeof chunk.meta.request_id === 'string') {
                patch(targetId, { requestId: chunk.meta.request_id });
              }
              if (chunk.delta) {
                setMessages(prev =>
                  prev.map(m =>
                    m.id === targetId
                      ? { ...m, content: m.content + chunk.delta }
                      : m,
                  ),
                );
              }
              if (chunk.end) {
                patch(targetId, { status: 'done', usage: chunk.usage ?? null });
              }
            },
          },
        );
      } catch (e) {
        const aborted = (e as DOMException)?.name === 'AbortError';
        patch(targetId, {
          status: 'failed',
          error: aborted ? '已中止' : String(e),
        });
      } finally {
        abortRef.current = null;
      }
    },
    [params, patch],
  );

  const requireModel = useCallback((): boolean => {
    if (!params.model_id) {
      onError('请先选择模型');
      return false;
    }
    return true;
  }, [params.model_id, onError]);

  const send = useCallback(
    async (text: string, attachments: UploadResult[]) => {
      if (!requireModel()) return;
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
        id: newId(),
        role: 'user',
        content: text,
        attachments: userAttachments,
      };
      const aiMsg: PlaygroundMessage = {
        id: newId(),
        role: 'assistant',
        content: '',
        status: 'streaming',
      };
      setMessages(prev => [...prev, userMsg, aiMsg]);
      await runInvoke(toReqMessages([...messages, userMsg]), aiMsg.id);
    },
    [messages, requireModel, runInvoke],
  );

  const deleteMessage = useCallback((id: string) => {
    setMessages(prev => {
      const idx = prev.findIndex(m => m.id === id);
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
    });
  }, []);

  const editMessage = useCallback(
    async (id: string, nextContent: string) => {
      if (!requireModel()) return;
      const idx = messages.findIndex(m => m.id === id);
      if (idx < 0 || messages[idx].role !== 'user') return;

      const replacedUser: PlaygroundMessage = {
        ...messages[idx],
        content: nextContent,
      };
      const newAssistant: PlaygroundMessage = {
        id: newId(),
        role: 'assistant',
        content: '',
        status: 'streaming',
      };
      const oldAssistant =
        idx + 1 < messages.length && messages[idx + 1].role === 'assistant'
          ? messages[idx + 1]
          : null;
      setMessages([
        ...messages.slice(0, idx),
        replacedUser,
        ...(oldAssistant ? [{ ...oldAssistant, stale: true }] : []),
        newAssistant,
      ]);
      const history = [
        ...messages.slice(0, idx).filter(m => !m.stale),
        replacedUser,
      ];
      await runInvoke(toReqMessages(history), newAssistant.id);
    },
    [messages, requireModel, runInvoke],
  );

  const regenerate = useCallback(
    async (id: string) => {
      if (!requireModel()) return;
      const idx = messages.findIndex(m => m.id === id);
      if (idx < 0 || messages[idx].role !== 'assistant') return;
      let userIdx = idx - 1;
      while (userIdx >= 0 && messages[userIdx].role !== 'user') userIdx--;
      if (userIdx < 0) {
        onError('找不到对应的 user 消息');
        return;
      }
      const newAssistant: PlaygroundMessage = {
        id: newId(),
        role: 'assistant',
        content: '',
        status: 'streaming',
      };
      setMessages([
        ...messages.slice(0, idx),
        { ...messages[idx], stale: true },
        newAssistant,
      ]);
      const history = messages.slice(0, idx).filter(m => !m.stale);
      await runInvoke(toReqMessages(history), newAssistant.id);
    },
    [messages, requireModel, onError, runInvoke],
  );

  /** 翻译：一次性请求，把译文流入一条新 assistant 消息（插在源消息后） */
  const translate = useCallback(
    async (id: string, lang?: string) => {
      if (!requireModel()) return;
      const idx = messages.findIndex(m => m.id === id);
      if (idx < 0 || !messages[idx].content.trim()) return;
      const target = lang ?? 'English';
      const out: PlaygroundMessage = {
        id: newId(),
        role: 'assistant',
        content: '',
        status: 'streaming',
      };
      setMessages(prev => [
        ...prev.slice(0, idx + 1),
        out,
        ...prev.slice(idx + 1),
      ]);
      await runInvoke(
        [{ role: 'user', content: messages[idx].content }],
        out.id,
        {
          system_prompt: `你是专业翻译引擎。把用户内容翻译成 ${target}，只输出译文，不要解释。`,
        },
      );
    },
    [messages, requireModel, runInvoke],
  );

  /** 继续生成：基于 history（含目标 assistant）续写，流入同一条消息 */
  const continueGen = useCallback(
    async (id: string) => {
      if (!requireModel()) return;
      const idx = messages.findIndex(m => m.id === id);
      if (idx < 0 || messages[idx].role !== 'assistant') return;
      patch(id, { status: 'streaming' });
      const history = messages.slice(0, idx + 1).filter(m => !m.stale);
      const req = toReqMessages(history);
      req.push({ role: 'user', content: '请接着上面的内容继续写完，不要重复。' });
      await runInvoke(req, id);
    },
    [messages, requireModel, patch, runInvoke],
  );

  const setFeedback = useCallback(
    (id: string, value: 1 | -1 | null) => {
      patch(id, { feedback: value });
      const msg = messages.find(m => m.id === id);
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
          .catch(() => onError('反馈写入失败'));
      }
    },
    [messages, patch, onError],
  );

  const setPinned = useCallback(
    (id: string, next: boolean) => patch(id, { pinned: next }),
    [patch],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const clear = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
  }, []);

  return {
    messages,
    streaming,
    send,
    stop,
    clear,
    deleteMessage,
    editMessage,
    regenerate,
    translate,
    continueGen,
    setFeedback,
    setPinned,
  };
}
