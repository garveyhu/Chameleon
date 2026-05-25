/** iframe / 公开对话页 —— /embed/:embedKey
 *
 * 两种用法共用本页：
 *   1. 业务方 <iframe src=".../embed/{key}"> 嵌进自家页面
 *   2. 「对话页打开」在新标签直接作为公开聊天页访问
 * 居中单列布局（窄屏铺满、宽屏不发散），流式渲染 assistant 回答。
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';

import { Bot, Send } from 'lucide-react';

import { MessageActions } from '@/core/components/chat';
import { Markdown } from '@/core/components/chat/markdown';
import { useEmbedChat } from '@/system/embed_iframe/hooks/use-embed-chat';
import type { ChatMessage } from '@/system/embed_iframe/types/embed-iframe';

export const EmbedIframePage = () => {
  const { embedKey } = useParams<{ embedKey: string }>();
  if (!embedKey) {
    return <FullCenter>缺少 embed_key</FullCenter>;
  }
  return <EmbedIframeView embedKey={embedKey} />;
};

const EmbedIframeView = ({ embedKey }: { embedKey: string }) => {
  const { config, messages, loading, sending, loadError, send } = useEmbedChat(embedKey);
  const [input, setInput] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  const ui = config?.ui_config || {};
  const primary = ui.primary_color || '#6366f1';
  const emoji = ui.icon_emoji || '';
  const title = ui.title || config?.name || 'Chameleon 助手';
  const subtitle = ui.subtitle || config?.description || '';
  const placeholder = config?.behavior?.placeholder || '输入消息……';
  const suggestions = config?.behavior?.suggested_questions || [];
  const showActions = config?.behavior?.show_feedback !== false;
  const askedYet = messages.some(m => m.role === 'user');

  useEffect(() => {
    requestAnimationFrame(() => {
      if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    });
  }, [messages]);

  const styleVars = useMemo(() => ({ '--primary': primary }) as React.CSSProperties, [primary]);

  if (loading) {
    return <FullCenter>加载中…</FullCenter>;
  }
  if (loadError) {
    return (
      <FullCenter>
        <div className="text-rose-600">加载失败：{loadError}</div>
      </FullCenter>
    );
  }

  return (
    <div className="flex h-screen w-screen flex-col bg-stone-50" style={styleVars}>
      {/* 头部 —— 干净白底 + 应用头像，避免整条彩色塑料感 */}
      <header className="flex items-center gap-3 border-b border-stone-200 bg-white px-4 py-2.5">
        <span
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-[18px] text-white"
          style={{ background: primary }}
        >
          {emoji || <Bot className="h-5 w-5" />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[14px] font-semibold text-stone-900">{title}</div>
          {subtitle && <div className="truncate text-[11.5px] text-stone-500">{subtitle}</div>}
        </div>
        <span className="flex items-center gap-1.5 text-[11px] text-stone-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          在线
        </span>
      </header>

      {/* 消息区 —— 居中单列 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-3 px-4 py-5">
          {messages.map(m => (
            <MessageBubble
              key={m.id}
              msg={m}
              primary={primary}
              emoji={emoji}
              showActions={showActions}
            />
          ))}
          {suggestions.length > 0 && !askedYet && (
            <div className="mt-1 flex flex-wrap gap-2 pl-11">
              {suggestions.map(q => (
                <button
                  key={q}
                  type="button"
                  disabled={sending}
                  onClick={() => void send(q)}
                  className="rounded-full border bg-white px-3 py-1.5 text-[12.5px] transition hover:shadow-sm disabled:opacity-50"
                  style={{ borderColor: primary, color: primary }}
                >
                  {q}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 输入区 —— 居中单列、悬浮卡片 */}
      <div className="bg-stone-50 px-4 pb-3">
        <div className="mx-auto w-full max-w-3xl">
          <Composer
            value={input}
            onChange={setInput}
            onSend={async () => {
              const v = input;
              setInput('');
              await send(v);
            }}
            placeholder={placeholder}
            disabled={sending}
            primary={primary}
          />
          <div className="pt-1.5 text-center text-[10.5px] text-stone-400">
            powered by Chameleon
          </div>
        </div>
      </div>
    </div>
  );
};

const MessageBubble = ({
  msg,
  primary,
  emoji,
  showActions,
}: {
  msg: ChatMessage;
  primary: string;
  emoji: string;
  showActions: boolean;
}) => {
  const isUser = msg.role === 'user';
  const withActions = showActions && !isUser && !msg.pending && !msg.error;

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div
          className="max-w-[80%] rounded-2xl rounded-br-sm px-3.5 py-2 text-[13.5px] leading-relaxed break-words text-white"
          style={{ background: primary }}
        >
          <span className="whitespace-pre-wrap">{msg.content}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="group flex items-start gap-2.5">
      <span
        className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[15px] text-white"
        style={{ background: primary }}
      >
        {emoji || <Bot className="h-4 w-4" />}
      </span>
      <div className="flex min-w-0 flex-col items-start">
        <div
          className={`max-w-full rounded-2xl rounded-tl-sm px-3.5 py-2 text-[13.5px] leading-relaxed break-words ${
            msg.error
              ? 'border border-rose-200 bg-rose-50 text-rose-700'
              : 'border border-stone-200 bg-white text-stone-800 shadow-sm'
          }`}
        >
          {msg.pending && !msg.content ? (
            <TypingDots />
          ) : msg.error ? (
            <span className="whitespace-pre-wrap">{msg.content}</span>
          ) : (
            <Markdown content={msg.content} />
          )}
        </div>
        {withActions && (
          <div className="mt-1">
            <MessageActions
              msg={{ id: msg.id, role: 'assistant', content: msg.content }}
              hidden={['export']}
            />
          </div>
        )}
      </div>
    </div>
  );
};

const TypingDots = () => (
  <span className="inline-flex gap-1 py-1">
    {[0, 1, 2].map(i => (
      <span
        key={i}
        className="h-1.5 w-1.5 animate-bounce rounded-full bg-stone-400"
        style={{ animationDelay: `${i * 0.12}s` }}
      />
    ))}
  </span>
);

const Composer = ({
  value,
  onChange,
  onSend,
  placeholder,
  disabled,
  primary,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  placeholder: string;
  disabled: boolean;
  primary: string;
}) => {
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (taRef.current) {
      taRef.current.style.height = 'auto';
      taRef.current.style.height = Math.min(taRef.current.scrollHeight, 140) + 'px';
    }
  }, [value]);

  return (
    <div className="flex items-end gap-2 rounded-2xl border border-stone-200 bg-white p-2 shadow-sm focus-within:border-stone-300">
      <textarea
        ref={taRef}
        rows={1}
        value={value}
        onChange={e => onChange(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!disabled && value.trim()) onSend();
          }
        }}
        placeholder={placeholder}
        disabled={disabled}
        className="flex-1 resize-none bg-transparent px-2 py-1.5 text-[13.5px] outline-none disabled:opacity-60"
      />
      <button
        type="button"
        onClick={onSend}
        disabled={disabled || !value.trim()}
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-white transition-opacity disabled:opacity-40"
        style={{ background: primary }}
        aria-label="发送"
      >
        <Send className="h-4 w-4" />
      </button>
    </div>
  );
};

const FullCenter = ({ children }: { children: React.ReactNode }) => (
  <div className="flex h-screen w-screen items-center justify-center text-sm text-stone-500">
    {children}
  </div>
);
