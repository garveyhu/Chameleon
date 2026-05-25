/** iframe 对话状态 hook —— session + 消息流 + 错误处理 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { embedIframeApi } from '@/system/embed_iframe/services/embed-iframe';
import type {
  ChatMessage,
  EmbedStreamChunk,
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
  const abortRef = useRef<AbortController | null>(null);

  const nextId = () => `m${++msgSeq.current}`;

  // 卸载时中断在途流
  useEffect(() => () => abortRef.current?.abort(), []);

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

      const patch = (fn: (m: ChatMessage) => ChatMessage) =>
        setMessages(prev => prev.map(m => (m.id === pendingId ? fn(m) : m)));

      const ctrl = new AbortController();
      abortRef.current = ctrl;
      let acc = '';
      let errMsg: string | null = null;
      const onChunk = (ch: EmbedStreamChunk) => {
        if (typeof ch.delta === 'string' && ch.delta) {
          acc += ch.delta;
          patch(m => ({ ...m, content: acc, pending: false }));
        } else if (ch.error) {
          errMsg = ch.error.message || '调用失败';
        } else if (ch.end && !acc && typeof ch.answer === 'string') {
          acc = ch.answer;
          patch(m => ({ ...m, content: acc, pending: false }));
        }
      };

      try {
        const token = await ensureSession();
        try {
          await embedIframeApi.streamInvoke(embedKey, token, trimmed, {
            signal: ctrl.signal,
            onChunk,
          });
        } catch (e) {
          // 尚无输出时多半是 session 失效 → 重签一次重试
          if (acc) throw e;
          session.current = null;
          const fresh = await ensureSession();
          await embedIframeApi.streamInvoke(embedKey, fresh, trimmed, {
            signal: ctrl.signal,
            onChunk,
          });
        }
        if (errMsg) {
          patch(m => ({ ...m, content: errMsg as string, pending: false, error: true }));
        } else {
          patch(m => ({ ...m, pending: false }));
        }
      } catch (e) {
        if (ctrl.signal.aborted) return;
        const msg = e instanceof Error ? e.message : '调用失败，请稍后重试';
        patch(m => ({ ...m, content: msg, pending: false, error: true }));
      } finally {
        setSending(false);
      }
    },
    [embedKey, ensureSession, sending],
  );

  return { config, messages, loading, sending, loadError, send };
}
