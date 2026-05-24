/** ChatDebugDialog —— 把当前工作流 draft 当可对话 agent 多轮调试（Dify Chatflow 风）
 *
 * 走 /v1/admin/graphs/{id}/chat/stream：临时会话、不落库、不必先发布。
 * history 客户端管理；delta 累积成回答，step 显示执行过程。dirty 时跑前自动存草稿。
 */

import { Eraser, Send } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { Button } from '@/core/components/ui/button';
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalHeader,
  ModalTitle,
} from '@/core/components/ui/modal';
import { StatusBadge } from '@/core/components/ui/status-badge';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { graphApi } from '@/system/graphs/services/graph';
import type { GraphChatTurn } from '@/system/graphs/services/graph';

interface StepLine {
  name: string;
  status: string;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  steps?: StepLine[];
  error?: string;
  streaming?: boolean;
}

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  graphId: string;
  graphName: string;
  isDirty: boolean;
  save: () => Promise<void>;
}

export const ChatDebugDialog = ({
  open,
  onOpenChange,
  graphId,
  graphName,
  isDirty,
  save,
}: Props) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // P5-2：跨轮会话变量（客户端携带；assign 节点经 done 回传后更新）
  const convVarsRef = useRef<Record<string, unknown>>({});

  // 卸载时中断在途流
  useEffect(() => () => abortRef.current?.abort(), []);
  // 新消息滚到底（DOM 操作，非 setState）
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const patchLast = (fn: (m: ChatMessage) => ChatMessage) =>
    setMessages(ms =>
      ms.map((m, i) => (i === ms.length - 1 ? fn(m) : m)),
    );

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;

    if (isDirty) {
      try {
        await save();
      } catch {
        return; // 存草稿失败：editor 的 saveMut 不弹错，这里直接放弃发送
      }
    }

    const history: GraphChatTurn[] = messages
      .filter(m => !m.error)
      .map(m => ({ role: m.role, content: m.content }));

    setMessages(ms => [
      ...ms,
      { role: 'user', content: text },
      { role: 'assistant', content: '', steps: [], streaming: true },
    ]);
    setInput('');
    setBusy(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      await graphApi.chatStream(
        graphId,
        { message: text, history, conversation_vars: convVarsRef.current },
        {
          signal: ctrl.signal,
          onChunk: chunk => {
            if (chunk.type === 'delta') {
              const t = chunk.data.text ?? '';
              if (t) patchLast(m => ({ ...m, content: m.content + t }));
            } else if (chunk.type === 'step') {
              const name = String(chunk.data.name ?? '');
              const status = String(chunk.data.status ?? '');
              patchLast(m => {
                const steps = [...(m.steps ?? [])];
                const idx = steps.findIndex(s => s.name === name);
                if (idx >= 0) steps[idx] = { name, status };
                else steps.push({ name, status });
                return { ...m, steps };
              });
            } else if (chunk.type === 'done') {
              const ans = chunk.data.answer;
              const cv = chunk.data.conversation_vars;
              if (cv && typeof cv === 'object') {
                convVarsRef.current = cv as Record<string, unknown>;
              }
              patchLast(m => ({
                ...m,
                content: m.content || (typeof ans === 'string' ? ans : ''),
                streaming: false,
              }));
            } else if (chunk.type === 'error') {
              patchLast(m => ({
                ...m,
                error: String(chunk.data.message ?? '执行失败'),
                streaming: false,
              }));
            }
          },
        },
      );
    } catch (e) {
      if (!ctrl.signal.aborted) {
        patchLast(m => ({
          ...m,
          error: (e as Error).message,
          streaming: false,
        }));
      }
    } finally {
      patchLast(m => ({ ...m, streaming: false }));
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onOpenChange={onOpenChange}>
      <ModalContent
        size="lg"
        className="flex h-[82vh] flex-col"
        closeOnBackdrop={false}
      >
        <ModalHeader>
          <ModalTitle>对话调试 · {graphName}</ModalTitle>
        </ModalHeader>
        <ModalBody className="flex min-h-0 flex-1 flex-col gap-0 !p-0">
          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
            {messages.length === 0 ? (
              <div className="py-12 text-center text-[12px] text-stone-400">
                把当前画布（draft）当可对话 agent 试聊；不落库、不必先发布。
                {isDirty && (
                  <div className="mt-1 text-[10.5px] text-amber-600">
                    有未保存改动 —— 发送前会先自动存草稿。
                  </div>
                )}
              </div>
            ) : (
              messages.map((m, i) => <Bubble key={i} m={m} />)
            )}
          </div>
          <div className="flex items-end gap-2 border-t border-stone-200/70 p-3">
            <Textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              rows={2}
              placeholder="输入消息，Enter 发送（Shift+Enter 换行）"
              className="flex-1 resize-none text-[12.5px]"
              disabled={busy}
            />
            <div className="flex flex-col gap-1.5">
              <Button size="sm" onClick={() => void send()} disabled={busy || !input.trim()}>
                <Send className="mr-1 h-3 w-3" />
                发送
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setMessages([]);
                  convVarsRef.current = {};
                }}
                disabled={busy || messages.length === 0}
                title="清空对话"
              >
                <Eraser className="mr-1 h-3 w-3" />
                清空
              </Button>
            </div>
          </div>
        </ModalBody>
      </ModalContent>
    </Modal>
  );
};

const STEP_TONE = (status: string) =>
  status === 'success' ? 'success' : status === 'failed' ? 'error' : 'running';

const Bubble = ({ m }: { m: ChatMessage }) => {
  if (m.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-blue-600 px-3 py-2 text-[12.5px] text-white">
          {m.content}
        </div>
      </div>
    );
  }
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] space-y-1.5">
        {m.steps && m.steps.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {m.steps.map((s, i) => (
              <StatusBadge
                key={i}
                tone={STEP_TONE(s.status)}
                pulse={s.status === 'running'}
              >
                {s.name}
              </StatusBadge>
            ))}
          </div>
        )}
        {m.error ? (
          <div className="rounded-2xl rounded-bl-sm border border-rose-200 bg-rose-50 px-3 py-2 text-[12.5px] text-rose-700">
            {m.error}
          </div>
        ) : (
          <div
            className={cn(
              'whitespace-pre-wrap rounded-2xl rounded-bl-sm border border-stone-200 bg-white px-3 py-2 text-[12.5px] text-stone-800',
              m.streaming && !m.content && 'text-stone-400',
            )}
          >
            {m.content || (m.streaming ? '思考中…' : '')}
          </div>
        )}
      </div>
    </div>
  );
};
