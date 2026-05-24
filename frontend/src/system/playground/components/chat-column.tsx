/** Playground 单列：参数 panel + 消息流 + 输入框 + 发送/停止
 *
 * 列状态 / 消息动作全在 core/stores/chat（按 columnId）；本组件管输入态 + 渲染。
 */

import { Download, Send, Square, Trash2 } from 'lucide-react';
import { useCallback, useState } from 'react';

import { MessageActions } from '@/core/components/chat';
import type {
  ChatActionMessage,
  MessageActionHandlers,
  TranslateLanguage,
} from '@/core/components/chat';
import { VirtualList } from '@/core/components/common/virtual-list';
import { Button } from '@/core/components/ui/button';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import {
  isStreaming,
  messagesOf,
  paramsOf,
  useChatStore,
} from '@/core/stores/chat';
import { FileAttachButton } from '@/system/playground/components/file-attach-button';
import { ParamPanel } from '@/system/playground/components/param-panel';
import type { PlaygroundMessage } from '@/system/playground/types/playground';
import type { UploadResult } from '@/system/files/services/file-upload';

const TRANSLATE_LANGUAGES: TranslateLanguage[] = [
  { code: 'English', label: '英语' },
  { code: '简体中文', label: '简体中文' },
  { code: '日本語', label: '日语' },
  { code: '한국어', label: '韩语' },
  { code: 'Français', label: '法语' },
];

interface Props {
  columnId: string;
  /** 多列模式下用作 key + 标题；单列模式留空 */
  index?: number;
  onRemove?: () => void;
  className?: string;
}

export const ChatColumn = ({ columnId, index, onRemove, className }: Props) => {
  const params = useChatStore(s => paramsOf(s, columnId));
  const messages = useChatStore(s => messagesOf(s, columnId));
  const streaming = useChatStore(s => isStreaming(s, columnId));
  const updateParams = useChatStore(s => s.updateParams);
  const send = useChatStore(s => s.send);
  const stop = useChatStore(s => s.stop);
  const clearMessages = useChatStore(s => s.clearMessages);

  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState<UploadResult[]>([]);

  const doSend = useCallback(async () => {
    const text = input.trim();
    if (!text && attachments.length === 0) return;
    setInput('');
    setAttachments([]);
    await send(columnId, text, attachments);
  }, [input, attachments, send, columnId]);

  const exportMd = useCallback(() => {
    const md = messages
      .map(m => {
        const head =
          m.role === 'user'
            ? '## 🧑 User'
            : m.role === 'assistant'
              ? '## 🤖 Assistant'
              : '## ⚙️ System';
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

  if (!params) return null;

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
            onClick={() => clearMessages(columnId)}
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
        <ParamPanel
          params={params}
          onChange={next => updateParams(columnId, next)}
        />
      </div>

      {messages.length === 0 ? (
        <div className="flex flex-1 items-center justify-center p-3 text-[12px] text-stone-400">
          输入消息开始对话
        </div>
      ) : (
        <VirtualList
          items={messages}
          getKey={m => m.id}
          estimateSize={88}
          stickToBottom
          className="flex-1 px-3 pt-3"
          itemClassName="pb-2"
          renderItem={m => <MessageBubble columnId={columnId} msg={m} />}
        />
      )}

      <footer className="border-t border-stone-200/70 p-2">
        <Textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              doSend();
            }
          }}
          rows={2}
          placeholder="输入消息… ⌘/Ctrl+Enter 发送"
          className="text-[12.5px]"
        />
        <div className="mt-1.5 flex items-center gap-2">
          <FileAttachButton
            attachments={attachments}
            onAttached={a => setAttachments(prev => [...prev, a])}
            onRemove={id =>
              setAttachments(prev => prev.filter(a => a.object_id !== id))
            }
            disabled={streaming}
          />
          <div className="ml-auto flex items-center gap-2">
            {streaming ? (
              <Button size="sm" variant="ghost" onClick={() => stop(columnId)}>
                <Square className="mr-1 h-3 w-3" />
                停止
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={doSend}
                disabled={!input.trim() && attachments.length === 0}
              >
                <Send className="mr-1 h-3 w-3" />
                发送
              </Button>
            )}
          </div>
        </div>
      </footer>
    </div>
  );
};

const toActionMessage = (m: PlaygroundMessage): ChatActionMessage => ({
  id: m.id,
  role: m.role,
  content: m.content,
  status: m.status,
  feedback: m.feedback,
  pinned: m.pinned,
});

const MessageBubble = ({
  columnId,
  msg,
}: {
  columnId: string;
  msg: PlaygroundMessage;
}) => {
  const isUser = msg.role === 'user';
  const [editing, setEditing] = useState(false);
  const [editVal, setEditVal] = useState(msg.content);

  const editMessage = useChatStore(s => s.editMessage);
  const regenerate = useChatStore(s => s.regenerate);
  const deleteMessage = useChatStore(s => s.deleteMessage);
  const setFeedback = useChatStore(s => s.setFeedback);
  const translate = useChatStore(s => s.translate);
  const continueGen = useChatStore(s => s.continueGen);
  const setPinned = useChatStore(s => s.setPinned);

  const handlers: MessageActionHandlers = {
    onEdit: isUser ? () => setEditing(true) : undefined,
    onRegenerate:
      msg.role === 'assistant'
        ? () => void regenerate(columnId, msg.id)
        : undefined,
    onDelete: () => deleteMessage(columnId, msg.id),
    onFeedback: value => setFeedback(columnId, msg.id, value),
    onTranslate: lang => void translate(columnId, msg.id, lang),
    onContinue:
      msg.role === 'assistant'
        ? () => void continueGen(columnId, msg.id)
        : undefined,
    onPin: next => setPinned(columnId, msg.id, next),
  };

  return (
    <div
      className={cn(
        'group relative rounded-md px-3 py-2 text-[12.5px] transition',
        isUser ? 'bg-amber-50/70' : 'bg-stone-50',
        msg.status === 'failed' && 'bg-rose-50',
        msg.pinned && 'ring-1 ring-amber-300',
        msg.stale && 'opacity-50',
      )}
    >
      <div className="mb-0.5 flex items-center justify-between">
        <div className="text-[10.5px] uppercase tracking-wider text-stone-500">
          {msg.role}
          {msg.pinned && <span className="ml-2 text-amber-600">📌</span>}
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
              msg={toActionMessage(msg)}
              handlers={handlers}
              translateLanguages={TRANSLATE_LANGUAGES}
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
                await editMessage(columnId, msg.id, next);
              }}
              disabled={!editVal.trim()}
            >
              提交并重发
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-1.5">
          {msg.attachments && msg.attachments.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {msg.attachments.map(a => (
                <AttachmentPreview key={a.object_id} attachment={a} />
              ))}
            </div>
          )}
          <div className="whitespace-pre-wrap text-stone-800">
            {msg.content || (msg.status === 'streaming' ? '…' : '')}
            {msg.error && <div className="mt-1 text-rose-600">{msg.error}</div>}
          </div>
        </div>
      )}
    </div>
  );
};

const AttachmentPreview = ({
  attachment,
}: {
  attachment: NonNullable<PlaygroundMessage['attachments']>[number];
}) => {
  if (attachment.mime_kind === 'image') {
    return (
      <a
        href={attachment.object_url}
        target="_blank"
        rel="noopener noreferrer"
        className="block overflow-hidden rounded-md border border-stone-200/70 transition hover:border-amber-300"
      >
        <img
          src={attachment.object_url}
          alt=""
          className="block h-24 w-24 object-cover"
        />
      </a>
    );
  }
  if (attachment.mime_kind === 'audio') {
    return (
      <audio
        controls
        src={attachment.object_url}
        className="h-8 max-w-[280px] rounded-md"
      />
    );
  }
  return (
    <a
      href={attachment.object_url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 rounded-md border border-stone-200/70 bg-stone-50/60 px-2 py-1 text-[11px] text-stone-700 hover:border-amber-300 hover:bg-amber-50/40"
    >
      {attachment.mime_kind ?? 'file'} · {attachment.object_id.split('/').pop()}
    </a>
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
