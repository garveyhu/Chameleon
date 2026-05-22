/** Playground 单列：参数 panel + 消息流 + 输入框 + 发送/停止 */

import { Download, Send, Square, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Button } from '@/core/components/ui/button';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
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

    const reqMessages = [...messages, userMsg].map(m => ({
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
                  m.id === aiMsg.id
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
            if (chunk.delta) {
              setMessages(prev =>
                prev.map(m =>
                  m.id === aiMsg.id
                    ? { ...m, content: m.content + chunk.delta }
                    : m,
                ),
              );
            }
            if (chunk.end) {
              setMessages(prev =>
                prev.map(m =>
                  m.id === aiMsg.id
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
          m.id === aiMsg.id
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
  }, [input, params, messages]);

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
          messages.map(m => <MessageBubble key={m.id} msg={m} />)
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

const MessageBubble = ({ msg }: { msg: PlaygroundMessage }) => {
  const isUser = msg.role === 'user';
  return (
    <div
      className={cn(
        'rounded-md px-3 py-2 text-[12.5px]',
        isUser ? 'bg-amber-50/70' : 'bg-stone-50',
        msg.status === 'failed' && 'bg-rose-50',
      )}
    >
      <div className="mb-0.5 text-[10.5px] uppercase tracking-wider text-stone-500">
        {msg.role}
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
      <div className="whitespace-pre-wrap text-stone-800">
        {msg.content || (msg.status === 'streaming' ? '…' : '')}
        {msg.error && (
          <div className="mt-1 text-rose-600">{msg.error}</div>
        )}
      </div>
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
