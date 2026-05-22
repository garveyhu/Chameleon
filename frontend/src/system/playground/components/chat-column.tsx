/** Playground 单列：参数 panel + 消息流 + 输入框 + 发送/停止 */

import { Download, Send, Square, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Button } from '@/core/components/ui/button';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import { MessageActions } from '@/system/playground/components/message-actions';
import { ParamPanel } from '@/system/playground/components/param-panel';
import { streamInvoke } from '@/system/playground/services/playground';
import type {
  InvokeChunk,
  PlaygroundMessage,
  PlaygroundParams,
} from '@/system/playground/types/playground';

const newId = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

interface Props {
  /** 多列模式下用作 key + 标题；单列模式留空 */
  index?: number;
  params: PlaygroundParams;
  onParamsChange: (next: PlaygroundParams) => void;
  onRemove?: () => void;
  className?: string;
}

export const ChatColumn = ({
  index,
  params,
  onParamsChange,
  onRemove,
  className,
}: Props) => {
  const [messages, setMessages] = useState<PlaygroundMessage[]>([]);
  const [input, setInput] = useState('');
  const abortRef = useRef<AbortController | null>(null);
  const streaming = useMemo(
    () => messages.some(m => m.status === 'streaming'),
    [messages],
  );

  const runInvoke = useCallback(
    async (history: PlaygroundMessage[], assistantId: string) => {
      const reqMessages = history.map(m => ({
        role: m.role,
        content: m.content,
      }));
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        await streamInvoke(
          {
            model_id: params.model_id,
            system_prompt: params.system_prompt || undefined,
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
                setMessages(prev =>
                  prev.map(m =>
                    m.id === assistantId
                      ? {
                          ...m,
                          status: 'failed',
                          error: `${chunk.error!.type}: ${chunk.error!.message}`,
                        }
                      : m,
                  ),
                );
                return;
              }
              if (chunk.meta) {
                const rid =
                  typeof chunk.meta.request_id === 'string'
                    ? chunk.meta.request_id
                    : undefined;
                if (rid) {
                  setMessages(prev =>
                    prev.map(m =>
                      m.id === assistantId ? { ...m, requestId: rid } : m,
                    ),
                  );
                }
              }
              if (chunk.delta) {
                setMessages(prev =>
                  prev.map(m =>
                    m.id === assistantId
                      ? { ...m, content: m.content + chunk.delta }
                      : m,
                  ),
                );
              }
              if (chunk.end) {
                setMessages(prev =>
                  prev.map(m =>
                    m.id === assistantId
                      ? { ...m, status: 'done', usage: chunk.usage ?? null }
                      : m,
                  ),
                );
              }
            },
          },
        );
      } catch (e) {
        const aborted = (e as DOMException)?.name === 'AbortError';
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId
              ? {
                  ...m,
                  status: 'failed',
                  error: aborted ? '已中止' : String(e),
                }
              : m,
          ),
        );
      } finally {
        abortRef.current = null;
      }
    },
    [params],
  );

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text) return;
    if (!params.model_id) {
      toast.error('请先选择模型');
      return;
    }
    const userMsg: PlaygroundMessage = {
      id: newId(),
      role: 'user',
      content: text,
    };
    const aiMsg: PlaygroundMessage = {
      id: newId(),
      role: 'assistant',
      content: '',
      status: 'streaming',
    };
    setMessages(prev => [...prev, userMsg, aiMsg]);
    setInput('');
    await runInvoke([...messages, userMsg], aiMsg.id);
  }, [input, params, messages, runInvoke]);

  /** 删除指定消息（user 同步删紧随其后的 assistant；assistant 单独删） */
  const deleteMessage = useCallback((id: string) => {
    setMessages(prev => {
      const idx = prev.findIndex(m => m.id === id);
      if (idx < 0) return prev;
      const target = prev[idx];
      if (target.role === 'user' && idx + 1 < prev.length && prev[idx + 1].role === 'assistant') {
        return prev.filter((_, i) => i !== idx && i !== idx + 1);
      }
      return prev.filter((_, i) => i !== idx);
    });
  }, []);

  /** 编辑 user 消息并重发（老 assistant 标记 stale） */
  const editMessage = useCallback(
    async (id: string, nextContent: string) => {
      if (!params.model_id) {
        toast.error('请先选择模型');
        return;
      }
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
      // 老 assistant（如果有）标 stale，保留可读
      const oldAssistant =
        idx + 1 < messages.length && messages[idx + 1].role === 'assistant'
          ? messages[idx + 1]
          : null;
      const next: PlaygroundMessage[] = [
        ...messages.slice(0, idx),
        replacedUser,
        ...(oldAssistant ? [{ ...oldAssistant, stale: true }] : []),
        newAssistant,
      ];
      setMessages(next);

      // history 用 replacedUser，但不含老 stale assistant（避免它干扰新一轮）
      const history = [
        ...messages.slice(0, idx).filter(m => !m.stale),
        replacedUser,
      ];
      await runInvoke(history, newAssistant.id);
    },
    [messages, params, runInvoke],
  );

  /** 对一条 assistant 消息重新生成（基于其前面的 user 消息） */
  const regenerateMessage = useCallback(
    async (id: string) => {
      if (!params.model_id) {
        toast.error('请先选择模型');
        return;
      }
      const idx = messages.findIndex(m => m.id === id);
      if (idx < 0 || messages[idx].role !== 'assistant') return;
      // 找前面那条 user
      let userIdx = idx - 1;
      while (userIdx >= 0 && messages[userIdx].role !== 'user') userIdx--;
      if (userIdx < 0) {
        toast.error('找不到对应的 user 消息');
        return;
      }
      const newAssistant: PlaygroundMessage = {
        id: newId(),
        role: 'assistant',
        content: '',
        status: 'streaming',
      };
      const next: PlaygroundMessage[] = [
        ...messages.slice(0, idx),
        { ...messages[idx], stale: true },
        newAssistant,
      ];
      setMessages(next);

      const history = messages.slice(0, idx).filter(m => !m.stale);
      await runInvoke(history, newAssistant.id);
    },
    [messages, params, runInvoke],
  );

  /** 更新消息（不重新调用 API，比如 feedback 状态） */
  const updateMessage = useCallback(
    (id: string, patch: Partial<PlaygroundMessage>) => {
      setMessages(prev =>
        prev.map(m => (m.id === id ? { ...m, ...patch } : m)),
      );
    },
    [],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const clearMsgs = useCallback(() => {
    if (streaming) {
      stop();
    }
    setMessages([]);
  }, [streaming, stop]);

  const exportMd = useCallback(() => {
    const md = messages
      .map(m => {
        const head =
          m.role === 'user' ? '## 🧑 User' : m.role === 'assistant' ? '## 🤖 Assistant' : '## ⚙️ System';
        return `${head}\n\n${m.content}`;
      })
      .join('\n\n---\n\n');
    download(md, `playground-${Date.now()}.md`);
  }, [messages]);

  const exportJson = useCallback(() => {
    download(
      JSON.stringify({ params, messages }, null, 2),
      `playground-${Date.now()}.json`,
    );
  }, [params, messages]);

  // 自动滚到底
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  return (
    <div
      className={cn(
        'flex h-full min-w-0 flex-col rounded-lg border border-stone-200/70 bg-white',
        className,
      )}
    >
      <header className="flex items-center justify-between border-b border-stone-200/70 px-3 py-2">
        <div className="text-[12.5px] font-medium text-stone-800">
          {index != null ? `列 ${index + 1}` : 'Playground'}
        </div>
        <div className="flex items-center gap-1 text-stone-500">
          <button
            type="button"
            title="导出 Markdown"
            className="rounded p-1 hover:bg-stone-100 hover:text-stone-800"
            onClick={exportMd}
            disabled={messages.length === 0}
          >
            <Download className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            title="导出 JSON"
            className="rounded p-1 font-mono text-[10px] hover:bg-stone-100 hover:text-stone-800"
            onClick={exportJson}
            disabled={messages.length === 0}
          >
            json
          </button>
          <button
            type="button"
            title="清空"
            className="rounded p-1 hover:bg-rose-50 hover:text-rose-600"
            onClick={clearMsgs}
            disabled={messages.length === 0}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
          {onRemove && (
            <button
              type="button"
              title="移除此列"
              className="rounded p-1 hover:bg-rose-50 hover:text-rose-600"
              onClick={onRemove}
            >
              ×
            </button>
          )}
        </div>
      </header>

      <div className="border-b border-stone-200/70 p-3">
        <ParamPanel params={params} onChange={onParamsChange} />
      </div>

      <div ref={scrollRef} className="flex-1 space-y-2 overflow-y-auto p-3">
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center text-[12px] text-stone-400">
            输入消息开始对话
          </div>
        ) : (
          messages.map(m => (
            <MessageBubble
              key={m.id}
              msg={m}
              onEdit={
                m.role === 'user'
                  ? next => editMessage(m.id, next)
                  : undefined
              }
              onRegenerate={
                m.role === 'assistant'
                  ? () => regenerateMessage(m.id)
                  : undefined
              }
              onDelete={() => deleteMessage(m.id)}
              onFeedbackChange={value => updateMessage(m.id, { feedback: value })}
            />
          ))
        )}
      </div>

      <footer className="border-t border-stone-200/70 p-2">
        <Textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              send();
            }
          }}
          rows={2}
          placeholder="输入消息… ⌘/Ctrl+Enter 发送"
          className="text-[12.5px]"
        />
        <div className="mt-1.5 flex justify-end gap-2">
          {streaming ? (
            <Button size="sm" variant="ghost" onClick={stop}>
              <Square className="mr-1 h-3 w-3" />
              停止
            </Button>
          ) : (
            <Button size="sm" onClick={send} disabled={!input.trim()}>
              <Send className="mr-1 h-3 w-3" />
              发送
            </Button>
          )}
        </div>
      </footer>
    </div>
  );
};

interface MessageBubbleProps {
  msg: PlaygroundMessage;
  onEdit?: (next: string) => void | Promise<void>;
  onRegenerate?: () => void | Promise<void>;
  onDelete?: () => void;
  onFeedbackChange?: (value: 1 | -1 | null) => void;
}

const MessageBubble = ({
  msg,
  onEdit,
  onRegenerate,
  onDelete,
  onFeedbackChange,
}: MessageBubbleProps) => {
  const isUser = msg.role === 'user';
  const [editing, setEditing] = useState(false);
  const [editVal, setEditVal] = useState(msg.content);

  return (
    <div
      className={cn(
        'group relative rounded-md px-3 py-2 text-[12.5px] transition',
        isUser ? 'bg-amber-50/70' : 'bg-stone-50',
        msg.status === 'failed' && 'bg-rose-50',
        msg.stale && 'opacity-50',
      )}
    >
      <div className="mb-0.5 flex items-center justify-between">
        <div className="text-[10.5px] uppercase tracking-wider text-stone-500">
          {msg.role}
          {msg.stale && <span className="ml-2 text-stone-400">stale</span>}
          {msg.status === 'streaming' && (
            <span className="ml-2 text-amber-600">streaming…</span>
          )}
          {msg.status === 'failed' && (
            <span className="ml-2 text-rose-600">failed</span>
          )}
          {msg.usage && (
            <span className="ml-2 font-mono tnum text-stone-400">
              ↑{msg.usage.input_tokens} ↓{msg.usage.output_tokens}
            </span>
          )}
        </div>
        {!editing && (
          <div className="absolute right-2 top-1.5">
            <MessageActions
              msg={msg}
              onEdit={onEdit ? () => setEditing(true) : undefined}
              onRegenerate={onRegenerate}
              onDelete={onDelete}
              onFeedbackChange={onFeedbackChange}
            />
          </div>
        )}
      </div>
      {editing ? (
        <div className="space-y-1.5">
          <Textarea
            value={editVal}
            onChange={e => setEditVal(e.target.value)}
            rows={3}
            className="text-[12.5px]"
            autoFocus
          />
          <div className="flex justify-end gap-1.5">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setEditing(false);
                setEditVal(msg.content);
              }}
            >
              取消
            </Button>
            <Button
              size="sm"
              onClick={async () => {
                const next = editVal.trim();
                if (!next || next === msg.content) {
                  setEditing(false);
                  return;
                }
                setEditing(false);
                await onEdit?.(next);
              }}
              disabled={!editVal.trim()}
            >
              提交并重发
            </Button>
          </div>
        </div>
      ) : (
        <div className="whitespace-pre-wrap text-stone-800">
          {msg.content || (msg.status === 'streaming' ? '…' : '')}
          {msg.error && (
            <div className="mt-1 text-rose-600">{msg.error}</div>
          )}
        </div>
      )}
    </div>
  );
};

function download(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
