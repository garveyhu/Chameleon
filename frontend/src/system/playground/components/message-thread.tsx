/** Playground 消息流 —— 气泡式渲染（视觉对齐嵌入式 widget）
 *
 * 供「单聊三栏」与「对比多列」共用。assistant 走共享 Markdown 渲染、user 纯文本；
 * bot 带头像 + 左上角 tail，user 实色气泡 + 右上角 tail；流式空内容显示打字指示。
 * 每条 assistant 消息在 footer 提供 trace 入口（onOpenTrace），方便调试阶段查问题。
 */

import { BookmarkPlus, Bot, ListTree } from 'lucide-react';
import { useState } from 'react';

import { MessageActions } from '@/core/components/chat';
import type {
  ChatActionMessage,
  MessageActionHandlers,
  TranslateLanguage,
} from '@/core/components/chat';
import { Markdown } from '@/core/components/chat/markdown';
import { VirtualList } from '@/core/components/common/virtual-list';
import { Button } from '@/core/components/ui/button';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { messagesOf, useChatStore } from '@/core/stores/chat';
import { SaveAsSampleModal } from '@/system/playground/components/save-as-sample-modal';
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
  onOpenTrace,
}: {
  columnId: string;
  className?: string;
  /** assistant 消息打开 trace（溯源）—— 由页面持有 TraceDrawer */
  onOpenTrace?: (msg: PlaygroundMessage) => void;
}) => {
  const messages = useChatStore(s => messagesOf(s, columnId));

  if (messages.length === 0) {
    return (
      <div
        className={cn(
          'flex flex-1 items-center justify-center text-[12px] text-stone-400',
          className,
        )}
      >
        输入消息开始对话
      </div>
    );
  }
  return (
    <VirtualList
      items={messages}
      getKey={m => m.id}
      estimateSize={72}
      stickToBottom
      className={cn('flex-1 px-4 pt-4', className)}
      itemClassName="pb-4"
      renderItem={m => (
        <MessageBubble
          columnId={columnId}
          msg={m}
          prevUserContent={prevUserOf(messages, m.id)}
          onOpenTrace={onOpenTrace}
        />
      )}
    />
  );
};

/** 找某条消息之前最近一条 user 消息文本（给「存为样本」预填输入） */
const prevUserOf = (msgs: PlaygroundMessage[], id: string): string => {
  const idx = msgs.findIndex(m => m.id === id);
  for (let i = idx - 1; i >= 0; i--) {
    if (msgs[i].role === 'user') return msgs[i].content;
  }
  return '';
};

const toActionMessage = (m: PlaygroundMessage): ChatActionMessage => ({
  id: m.id,
  role: m.role,
  content: m.content,
  status: m.status,
  feedback: m.feedback,
  pinned: m.pinned,
});

/** 流式待回复时的三点打字指示（对齐 widget .typing） */
const TypingDots = () => (
  <span className="inline-flex items-center gap-1 py-1" aria-label="生成中">
    {[0, 1, 2].map(i => (
      <span
        key={i}
        className="h-1.5 w-1.5 animate-bounce rounded-full bg-stone-400"
        style={{ animationDelay: `${i * 0.15}s` }}
      />
    ))}
  </span>
);

const MessageBubble = ({
  columnId,
  msg,
  prevUserContent,
  onOpenTrace,
}: {
  columnId: string;
  msg: PlaygroundMessage;
  prevUserContent?: string;
  onOpenTrace?: (msg: PlaygroundMessage) => void;
}) => {
  const isUser = msg.role === 'user';
  const [editing, setEditing] = useState(false);
  const [editVal, setEditVal] = useState(msg.content);
  const [saveOpen, setSaveOpen] = useState(false);

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

  // 编辑态：替换整条气泡为输入框（user 消息编辑后重发）
  if (editing) {
    return (
      <div className="flex flex-col gap-1.5 rounded-xl border border-stone-200 bg-white p-2">
        <Textarea
          value={editVal}
          onChange={e => setEditVal(e.target.value)}
          rows={3}
          className="text-[13px]"
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
    );
  }

  return (
    <div
      className={cn(
        'group flex gap-2',
        isUser ? 'flex-row-reverse' : 'flex-row',
        msg.stale && 'opacity-50',
      )}
    >
      {!isUser && (
        <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-blue-500 text-white">
          <Bot className="h-3.5 w-3.5" />
        </div>
      )}

      <div
        className={cn(
          'flex min-w-0 max-w-[88%] flex-col gap-1',
          isUser ? 'items-end' : 'items-start',
        )}
      >
        {msg.attachments && msg.attachments.length > 0 && (
          <div className={cn('flex flex-wrap gap-1.5', isUser && 'justify-end')}>
            {msg.attachments.map(a => (
              <AttachmentPreview key={a.object_id} attachment={a} />
            ))}
          </div>
        )}

        <div
          className={cn(
            'min-w-0 rounded-2xl px-3 py-2 text-[13px] leading-relaxed',
            isUser
              ? 'rounded-tr-sm bg-blue-600 text-white'
              : 'rounded-tl-sm border border-stone-200 bg-white text-stone-800 shadow-[0_1px_2px_rgba(0,0,0,0.04)]',
            msg.status === 'failed' && '!border-rose-200 !bg-rose-50 !text-rose-700',
            msg.pinned && 'ring-1 ring-amber-300',
          )}
        >
          {isUser ? (
            <div className="whitespace-pre-wrap break-words">{msg.content}</div>
          ) : msg.content ? (
            // user 气泡是实色背景，markdown 链接/代码沿用组件默认（bot 白底）样式
            <Markdown content={msg.content} />
          ) : msg.status === 'streaming' ? (
            <TypingDots />
          ) : (
            <span className="text-stone-400">（空回复）</span>
          )}
          {msg.error && <div className="mt-1 text-[12px] text-rose-600">{msg.error}</div>}
        </div>

        {/* footer：用量常显，trace + 动作 hover 浮现 */}
        <div
          className={cn(
            'flex items-center gap-2 px-1 text-[10px] text-stone-400',
            isUser ? 'flex-row-reverse' : 'flex-row',
          )}
        >
          {msg.pinned && <span className="text-amber-600">📌</span>}
          {msg.status === 'streaming' && <span className="text-blue-600">生成中…</span>}
          {msg.stale && <span>已替换</span>}
          {msg.usage && (
            <span className="tnum font-mono">
              ↑{msg.usage.input_tokens} ↓{msg.usage.output_tokens}
            </span>
          )}
          <div
            className={cn(
              'flex items-center gap-1 opacity-0 transition group-hover:opacity-100',
              isUser ? 'flex-row-reverse' : 'flex-row',
            )}
          >
            {!isUser && msg.requestId && onOpenTrace && (
              <button
                type="button"
                title="查看 trace（溯源调用链路）"
                onClick={() => onOpenTrace(msg)}
                className="flex items-center gap-0.5 rounded px-1 py-0.5 text-stone-400 transition hover:bg-violet-50 hover:text-violet-600"
              >
                <ListTree className="h-3 w-3" />
                trace
              </button>
            )}
            {!isUser && (
              <button
                type="button"
                title="存为评测样本（加入数据集）"
                onClick={() => setSaveOpen(true)}
                className="flex items-center gap-0.5 rounded px-1 py-0.5 text-stone-400 transition hover:bg-emerald-50 hover:text-emerald-600"
              >
                <BookmarkPlus className="h-3 w-3" />
                存样本
              </button>
            )}
            {saveOpen && (
              <SaveAsSampleModal
                defaultInput={prevUserContent ?? ''}
                defaultExpected={msg.content}
                onClose={() => setSaveOpen(false)}
              />
            )}
            <MessageActions
              msg={toActionMessage(msg)}
              handlers={handlers}
              translateLanguages={TRANSLATE_LANGUAGES}
            />
          </div>
        </div>
      </div>
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
        className="block overflow-hidden rounded-lg border border-stone-200/70 transition hover:border-blue-300"
      >
        <img src={attachment.object_url} alt="" className="block h-28 w-28 object-cover" />
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
      className="inline-flex items-center gap-1 rounded-full border border-stone-200/70 bg-stone-50/60 px-2.5 py-1 text-[11px] text-stone-700 transition hover:border-blue-300 hover:bg-blue-50/40"
    >
      📎 {attachment.object_id.split('/').pop()}
    </a>
  );
};
