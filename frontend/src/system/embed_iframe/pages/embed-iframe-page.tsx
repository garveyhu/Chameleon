/** iframe 全屏对话页 —— /embed/:embedKey
 *
 * 业务方 <iframe src=".../embed/{key}"> 嵌入到自家页面里使用。
 * 与 widget 共用后端 endpoints，但没有气泡按钮，永远展开。
 */

import { Send } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';

import { useEmbedChat } from '@/system/embed_iframe/hooks/use-embed-chat';

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
  const primary = ui.primary_color || '#0ea5e9';
  const title = ui.title || config?.name || 'Chameleon 助手';
  const subtitle = ui.subtitle || config?.description || '';
  const placeholder = config?.behavior?.placeholder || '输入消息……';

  // 自动滚到底
  useEffect(() => {
    requestAnimationFrame(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    });
  }, [messages]);

  // 顶层注入 primary color CSS 变量
  const styleVars = useMemo(() => ({ '--primary': primary } as React.CSSProperties), [primary]);

  if (loading) {
    return <FullCenter>加载中…</FullCenter>;
  }
  if (loadError) {
    return (
      <FullCenter>
        <div className="text-red-600">加载失败：{loadError}</div>
      </FullCenter>
    );
  }

  return (
    <div className="flex h-screen w-screen flex-col bg-stone-50" style={styleVars}>
      <header
        className="flex items-center justify-between px-4 py-3 text-white shadow-sm"
        style={{ background: primary }}
      >
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold">{title}</div>
          {subtitle && <div className="truncate text-xs opacity-85">{subtitle}</div>}
        </div>
      </header>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-4"
      >
        <div className="flex flex-col gap-2.5">
          {messages.map(m => (
            <MessageBubble key={m.id} msg={m} primary={primary} />
          ))}
        </div>
      </div>

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

      <div className="border-t border-stone-100 bg-white py-1.5 text-center text-[11px] text-stone-400">
        powered by Chameleon
      </div>
    </div>
  );
};

const MessageBubble = ({
  msg,
  primary,
}: {
  msg: { role: 'user' | 'assistant'; content: string; pending?: boolean; error?: boolean };
  primary: string;
}) => {
  const isUser = msg.role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] whitespace-pre-wrap break-words rounded-xl px-3 py-2 text-[13.5px] leading-relaxed ${
          isUser
            ? 'rounded-br-sm text-white'
            : msg.error
              ? 'rounded-bl-sm border border-red-200 bg-red-50 text-red-700'
              : 'rounded-bl-sm border border-stone-200 bg-white text-stone-800'
        }`}
        style={isUser ? { background: primary } : undefined}
      >
        {msg.pending ? <TypingDots /> : msg.content}
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
      taRef.current.style.height = Math.min(taRef.current.scrollHeight, 110) + 'px';
    }
  }, [value]);

  return (
    <div className="flex items-end gap-2 border-t border-stone-200 bg-white px-3 py-2">
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
        className="flex-1 resize-none rounded-lg border border-stone-300 px-2.5 py-2 text-[13.5px] outline-none focus:border-sky-500 disabled:bg-stone-100"
      />
      <button
        type="button"
        onClick={onSend}
        disabled={disabled || !value.trim()}
        className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg text-white transition-opacity disabled:opacity-45"
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
