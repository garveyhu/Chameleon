/** Playground 消息流 —— 按 columnId 渲染消息气泡（编辑 / 重生成 / 反馈 / 翻译 / 续写 / 钉）
 *
 * 从原 chat-column 拆出，供「单聊三栏」与「对比多列」两种布局共用。
 */

import { useState } from 'react';

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
import { messagesOf, useChatStore } from '@/core/stores/chat';
import type { PlaygroundMessage } from '@/system/playground/types/playground';

const TRANSLATE_LANGUAGES: TranslateLanguage[] = [
  { code: 'English', label: '英语' },
  { code: '简体中文', label: '简体中文' },
  { code: '日本語', label: '日语' },
  { code: '한국어', label: '韩语' },
  { code: 'Français', label: '法语' },
];

export const MessageThread = ({
  columnId,
  className,
}: {
  columnId: string;
  className?: string;
}) => {
  const messages = useChatStore(s => messagesOf(s, columnId));

  if (messages.length === 0) {
    return (
      <div className={cn('flex flex-1 items-center justify-center text-[12px] text-stone-400', className)}>
        输入消息开始对话
      </div>
    );
  }
  return (
    <VirtualList
      items={messages}
      getKey={m => m.id}
      estimateSize={88}
      stickToBottom
      className={cn('flex-1 px-3 pt-3', className)}
      itemClassName="pb-2"
      renderItem={m => <MessageBubble columnId={columnId} msg={m} />}
    />
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

const MessageBubble = ({ columnId, msg }: { columnId: string; msg: PlaygroundMessage }) => {
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
      msg.role === 'assistant' ? () => void regenerate(columnId, msg.id) : undefined,
    onDelete: () => deleteMessage(columnId, msg.id),
    onFeedback: value => setFeedback(columnId, msg.id, value),
    onTranslate: lang => void translate(columnId, msg.id, lang),
    onContinue:
      msg.role === 'assistant' ? () => void continueGen(columnId, msg.id) : undefined,
    onPin: next => setPinned(columnId, msg.id, next),
  };

  return (
    <div
      className={cn(
        'group relative rounded-md px-3 py-2 text-[12.5px] transition',
        isUser ? 'bg-blue-50/70' : 'bg-stone-50',
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
          {msg.status === 'streaming' && <span className="ml-2 text-blue-600">streaming…</span>}
          {msg.status === 'failed' && <span className="ml-2 text-rose-600">failed</span>}
          {msg.usage && (
            <span className="tnum ml-2 font-mono text-stone-400">
              ↑{msg.usage.input_tokens} ↓{msg.usage.output_tokens}
            </span>
          )}
        </div>
        {!editing && (
          <div className="absolute top-1.5 right-2">
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
        className="block overflow-hidden rounded-md border border-stone-200/70 transition hover:border-blue-300"
      >
        <img src={attachment.object_url} alt="" className="block h-24 w-24 object-cover" />
      </a>
    );
  }
  if (attachment.mime_kind === 'audio') {
    return <audio controls src={attachment.object_url} className="h-8 max-w-[280px] rounded-md" />;
  }
  return (
    <a
      href={attachment.object_url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 rounded-md border border-stone-200/70 bg-stone-50/60 px-2 py-1 text-[11px] text-stone-700 hover:border-blue-300 hover:bg-blue-50/40"
    >
      {attachment.mime_kind ?? 'file'} · {attachment.object_id.split('/').pop()}
    </a>
  );
};
