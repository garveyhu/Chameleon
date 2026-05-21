/** iframe 对话状态 hook —— session + 消息流 + 错误处理 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { embedIframeApi } from '@/system/embed_iframe/services/embed-iframe';
import type {
  ChatMessage,
  IframePublicConfig,
} from '@/system/embed_iframe/types/embed-iframe';

interface UseEmbedChatResult {
  config: IframePublicConfig | null;
  messages: ChatMessage[];
  loading: boolean;
  sending: boolean;
  loadError: string | null;
  send: (input: string) => Promise<void>;
}

interface SessionState {
  token: string;
  expiresAt: number;
}

export function useEmbedChat(embedKey: string): UseEmbedChatResult {
  const [config, setConfig] = useState<IframePublicConfig | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const session = useRef<SessionState | null>(null);
  const msgSeq = useRef(0);

  const nextId = () => `m${++msgSeq.current}`;

  const ensureSession = useCallback(async (): Promise<string> => {
    if (session.current && Date.now() < session.current.expiresAt - 30_000) {
      return session.current.token;
    }
    const res = await embedIframeApi.createSession(embedKey);
    session.current = {
      token: res.session_token,
      expiresAt: Date.now() + res.expires_in * 1000,
    };
    return session.current.token;
  }, [embedKey]);

  // 初次加载：拉配置 + welcome
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cfg = await embedIframeApi.getConfig(embedKey);
        if (cancelled) return;
        setConfig(cfg);
        const welcome = cfg.welcome_message || cfg.behavior?.welcome_message;
        if (welcome) {
          setMessages([{ id: nextId(), role: 'assistant', content: welcome }]);
        }
      } catch (e) {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : '加载失败';
          setLoadError(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [embedKey]);

  const send = useCallback(
    async (input: string) => {
      const trimmed = input.trim();
      if (!trimmed || sending) return;

      const userMsg: ChatMessage = { id: nextId(), role: 'user', content: trimmed };
      const pendingId = nextId();
      setMessages(prev => [
        ...prev,
        userMsg,
        { id: pendingId, role: 'assistant', content: '', pending: true },
      ]);
      setSending(true);

      try {
        const token = await ensureSession();
        let res;
        try {
          res = await embedIframeApi.invoke(embedKey, token, trimmed);
        } catch (e) {
          // session 失效 → 重签一次
          session.current = null;
          const fresh = await ensureSession();
          res = await embedIframeApi.invoke(embedKey, fresh, trimmed);
          void e;
        }
        setMessages(prev =>
          prev.map(m => (m.id === pendingId ? { ...m, content: res.answer, pending: false } : m)),
        );
      } catch (e) {
        const msg = e instanceof Error ? e.message : '调用失败，请稍后重试';
        setMessages(prev =>
          prev.map(m =>
            m.id === pendingId ? { ...m, content: msg, pending: false, error: true } : m,
          ),
        );
      } finally {
        setSending(false);
      }
    },
    [embedKey, ensureSession, sending],
  );

  return { config, messages, loading, sending, loadError, send };
}
