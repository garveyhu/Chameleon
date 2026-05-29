/** 会话详情页 —— 独立设计的「会话」组件（对齐 trace 详情质感）
 *
 * 三段式：身份头（标题 + 会话号 + 时间）→ 聚合 stat bar（运行 / Token / 成本 / 模型）
 * → 真实对话气泡（用户右 / 助手左，参考嵌入式 widget）。默认渲染最新一页，
 * 上滚到顶按页加载更早（保持视口位置），长会话不一次性渲染。
 */

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import {
  ArrowLeft,
  Check,
  Copy,
  Loader2,
  ListTree,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react';
import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { MessageActions } from '@/core/components/chat';
import type { ChatActionMessage, ChatActionRole } from '@/core/components/chat';
import { Markdown } from '@/core/components/chat/markdown';
import { StatBar, StatItem } from '@/core/components/common/stat-bar';
import { SectionCard } from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import { Textarea } from '@/core/components/ui/textarea';
import { cn } from '@/core/lib/cn';
import { formatCost, formatDateTime, formatTokens } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { conversationApi } from '@/system/conversations/services/conversation';
import type { MessageItem } from '@/system/conversations/types/message-tree';
import { TraceDrawer } from '@/system/call_logs/components/trace-drawer';
import { callLogApi } from '@/system/call_logs/services/call-log';
import type { CallLogItem } from '@/system/call_logs/types/call-log';

const PAGE_SIZE = 50;

const ROLE_LABEL: Record<string, string> = {
  user: '用户',
  assistant: '助手',
  system: '系统',
  tool: '工具',
};

const numOf = (u: Record<string, unknown> | null, k: string): number => {
  const v = u?.[k];
  return typeof v === 'number' ? v : 0;
};

export const ConversationDetailPage = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const sid = sessionId ?? '';

  const convQ = useQuery({
    queryKey: ['conversations', sid],
    queryFn: () => conversationApi.get(sid),
    enabled: !!sid,
  });

  // 先取总数（仅 1 行）→ 反向分页定位最后一页（最新）
  const metaQ = useQuery({
    queryKey: ['conversations', sid, 'messages-meta'],
    queryFn: () => conversationApi.listMessages(sid, { page: 1, page_size: 1 }),
    enabled: !!sid,
  });
  const total = metaQ.data?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // 从最新页起，往上滚按页加载更早（getNextPageParam 递减）
  const msgsQ = useInfiniteQuery({
    queryKey: ['conversations', sid, 'messages', lastPage],
    queryFn: ({ pageParam }) =>
      conversationApi.listMessages(sid, { page: pageParam, page_size: PAGE_SIZE }),
    initialPageParam: lastPage,
    getNextPageParam: (_last, _all, lastPageParam) =>
      lastPageParam > 1 ? lastPageParam - 1 : undefined,
    enabled: !!sid && total > 0,
  });

  const runsQ = useQuery({
    queryKey: ['conversations', sid, 'runs'],
    queryFn: () => callLogApi.list({ session_id: sid, page_size: 200 }),
    enabled: !!sid,
  });

  // 已加载页按 seq 升序展示（最新在底部）
  const messages = useMemo(() => {
    const all = (msgsQ.data?.pages ?? []).flatMap(p => p.items);
    return [...all].sort((a, b) => a.seq - b.seq);
  }, [msgsQ.data]);

  const runByReq = useMemo(() => {
    const m = new Map<string, CallLogItem>();
    (runsQ.data?.items ?? []).forEach(r => m.set(r.request_id, r));
    return m;
  }, [runsQ.data?.items]);

  const stats = useMemo(() => {
    const runs = runsQ.data?.items ?? [];
    const runTotal = runsQ.data?.total ?? runs.length;
    let tokens = runs.reduce((s, r) => s + (r.total_tokens ?? 0), 0);
    if (!tokens) {
      tokens = messages.reduce(
        (s, m) => s + numOf(m.usage, 'prompt_tokens') + numOf(m.usage, 'completion_tokens'),
        0,
      );
    }
    const hasCost = runs.some(r => r.cost_usd != null);
    const cost = runs.reduce((s, r) => s + (r.cost_usd ?? 0), 0);
    const models = Array.from(
      new Set(runs.map(r => r.model_code).filter((x): x is string => !!x)),
    );
    return { runTotal, tokens, cost, hasCost, models };
  }, [runsQ.data, messages]);

  const qc = useQueryClient();
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['conversations', sid] });
  };

  const regenMut = useMutation({
    mutationFn: (mid: EntityId) => conversationApi.regenerate(sid, mid),
    onSuccess: () => {
      toast.success('已生成新回复');
      refresh();
    },
    onError: e => toast.error('重新生成失败：' + (e as Error).message),
  });

  const editMut = useMutation({
    mutationFn: (p: { mid: EntityId; text: string }) =>
      conversationApi.editAndResend(sid, p.mid, p.text),
    onSuccess: () => {
      toast.success('已生成新回复');
      refresh();
      setEditingId(null);
    },
    onError: e => toast.error('编辑失败：' + (e as Error).message),
  });

  const [editingId, setEditingId] = useState<EntityId | null>(null);
  const [editText, setEditText] = useState('');
  const [copied, setCopied] = useState(false);
  const [traceLog, setTraceLog] = useState<CallLogItem | null>(null);

  // 滚动锚定：首屏滚到底（最新）；加载更早后保持视口位置（DOM 副作用，无 setState）
  const scrollRef = useRef<HTMLDivElement>(null);
  const prevHeight = useRef(0);
  const initedSid = useRef<string | null>(null);
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el || messages.length === 0) return;
    if (initedSid.current !== sid) {
      initedSid.current = sid;
      el.scrollTop = el.scrollHeight;
      prevHeight.current = el.scrollHeight;
      return;
    }
    if (prevHeight.current && el.scrollHeight > prevHeight.current) {
      el.scrollTop += el.scrollHeight - prevHeight.current;
    }
    prevHeight.current = el.scrollHeight;
  }, [messages.length, sid]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollTop <= 48 && msgsQ.hasNextPage && !msgsQ.isFetchingNextPage) {
      prevHeight.current = el.scrollHeight;
      void msgsQ.fetchNextPage();
    }
  };

  const copySid = () => {
    void navigator.clipboard.writeText(sid);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };

  if (!sid) {
    return (
      <SectionCard>
        <div className="p-6 text-sm text-stone-500">非法的 session_id</div>
      </SectionCard>
    );
  }

  const conv = convQ.data;
  const loading = metaQ.isLoading || (total > 0 && msgsQ.isLoading);

  return (
    <div className="space-y-3">
      {/* 身份头 + 聚合 stat bar */}
      <SectionCard className="!py-3">
        <div className="flex items-center gap-2">
          <Link
            to="/sessions"
            title="返回会话列表"
            className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> 会话
          </Link>
          <span className="text-stone-300">/</span>
          <span className="rounded bg-violet-50 px-1.5 py-0.5 font-mono text-[11px] text-violet-600">
            session
          </span>
          <span className="truncate text-[15px] font-semibold text-stone-900">
            {conv?.title || (convQ.isLoading ? '加载中…' : '未命名会话')}
          </span>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px]">
          <span className="inline-flex min-w-0 items-center gap-1">
            <span className="text-stone-400">会话</span>
            <button
              type="button"
              title="复制会话号"
              onClick={copySid}
              className="inline-flex items-center gap-1 font-mono text-stone-600 hover:text-blue-600"
            >
              {sid}
              {copied ? (
                <Check className="h-3 w-3 text-emerald-500" />
              ) : (
                <Copy className="h-3 w-3 opacity-50" />
              )}
            </button>
          </span>
          {conv && (
            <>
              <span>
                <span className="text-stone-400">创建</span>{' '}
                <span className="font-mono text-stone-600">{formatDateTime(conv.created_at)}</span>
              </span>
              {conv.last_message_at && (
                <span>
                  <span className="text-stone-400">最后活跃</span>{' '}
                  <span className="font-mono text-stone-600">
                    {formatDateTime(conv.last_message_at)}
                  </span>
                </span>
              )}
            </>
          )}
        </div>

        <div className="mt-3">
          <StatBar>
            <StatItem k="智能体" v={conv?.agent_key || '—'} mono />
            <StatItem k="终端用户" v={conv?.end_user_id || '匿名'} mono />
            <StatItem
              k="轮次"
              v={String(stats.runTotal)}
              sub={total ? `${total} 条消息` : undefined}
            />
            <StatItem k="Token" v={stats.tokens ? formatTokens(stats.tokens) : '—'} />
            <StatItem k="成本" v={stats.hasCost ? formatCost(stats.cost) : '—'} />
            <StatItem
              k="模型"
              v={stats.models[0] || '—'}
              sub={stats.models.length > 1 ? `+${stats.models.length - 1}` : undefined}
              mono
            />
          </StatBar>
        </div>
      </SectionCard>

      {/* 真实对话气泡 */}
      <SectionCard className="!p-0">
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="max-h-[calc(100vh-260px)] overflow-y-auto px-5 py-5"
        >
          {loading ? (
            <div className="py-12 text-center text-[12px] text-stone-400">加载消息中…</div>
          ) : messages.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-stone-400">暂无消息</div>
          ) : (
            <div className="space-y-5">
              {msgsQ.hasNextPage && (
                <div className="flex justify-center pb-1">
                  <button
                    type="button"
                    onClick={() => msgsQ.fetchNextPage()}
                    disabled={msgsQ.isFetchingNextPage}
                    className="inline-flex items-center gap-1.5 rounded-full border border-stone-200 bg-white px-3 py-1 text-[12px] text-stone-600 transition hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 disabled:opacity-50"
                  >
                    {msgsQ.isFetchingNextPage && <Loader2 className="h-3 w-3 animate-spin" />}
                    加载更早（已加载 {messages.length} / {total}）
                  </button>
                </div>
              )}
              {messages.map(msg => (
                <MessageBubble
                  key={String(msg.id)}
                  msg={msg}
                  run={msg.request_id ? runByReq.get(msg.request_id) : undefined}
                  onOpenTrace={setTraceLog}
                  isEditing={String(editingId) === String(msg.id)}
                  editText={editText}
                  setEditText={setEditText}
                  startEdit={() => {
                    setEditingId(msg.id);
                    setEditText(msg.content);
                  }}
                  cancelEdit={() => setEditingId(null)}
                  onRegenerate={() => regenMut.mutate(msg.id)}
                  onSubmitEdit={() => editMut.mutate({ mid: msg.id, text: editText })}
                  regenPending={regenMut.isPending}
                  editPending={editMut.isPending}
                />
              ))}
            </div>
          )}
        </div>
      </SectionCard>

      <TraceDrawer callLog={traceLog} onClose={() => setTraceLog(null)} />
    </div>
  );
};

interface MessageBubbleProps {
  msg: MessageItem;
  run?: CallLogItem;
  onOpenTrace: (run: CallLogItem) => void;
  isEditing: boolean;
  editText: string;
  setEditText: (s: string) => void;
  startEdit: () => void;
  cancelEdit: () => void;
  onRegenerate: () => void;
  onSubmitEdit: () => void;
  regenPending: boolean;
  editPending: boolean;
}

const MessageBubble = ({
  msg,
  run,
  onOpenTrace,
  isEditing,
  editText,
  setEditText,
  startEdit,
  cancelEdit,
  onRegenerate,
  onSubmitEdit,
  regenPending,
  editPending,
}: MessageBubbleProps) => {
  const role = msg.role;
  const isUser = role === 'user';
  const label = ROLE_LABEL[role] ?? role;

  return (
    <div className={cn('group/msg flex flex-col gap-1', isUser ? 'items-end' : 'items-start')}>
      {/* 元信息行 */}
      <div className="flex items-center gap-2 px-1 text-[10.5px] text-stone-400">
        <span className="font-medium text-stone-500">{label}</span>
        <span className="font-mono">#{msg.seq}</span>
        <span className="font-mono">{formatDateTime(msg.created_at)}</span>
        {msg.feedback === 1 && <ThumbsUp className="h-3 w-3 text-emerald-500" />}
        {msg.feedback === -1 && <ThumbsDown className="h-3 w-3 text-rose-500" />}
      </div>

      {/* 气泡：直角朝外上角（用户右上 / 助手左上），对齐嵌入式 widget */}
      {isEditing ? (
        <div className="w-full max-w-[78%] space-y-2">
          <Textarea
            value={editText}
            onChange={e => setEditText(e.target.value)}
            rows={4}
            className="font-mono text-[12.5px]"
          />
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={cancelEdit}>
              取消
            </Button>
            <Button size="sm" disabled={!editText.trim() || editPending} onClick={onSubmitEdit}>
              {editPending && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
              发送（新回复）
            </Button>
          </div>
        </div>
      ) : (
        <div
          className={cn(
            'max-w-[78%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed',
            isUser
              ? 'rounded-tr-sm bg-blue-600 whitespace-pre-wrap text-white'
              : 'rounded-tl-sm border border-stone-200 bg-white text-stone-800',
          )}
        >
          {isUser ? msg.content : <Markdown content={msg.content} />}
        </div>
      )}

      {/* 动作行：trace（常显） + copy / 编辑 / 重新生成（悬浮） */}
      {!isEditing && (
        <div
          className={cn(
            'flex items-center gap-1.5',
            isUser ? 'flex-row-reverse' : 'flex-row',
          )}
        >
          {run && (
            <button
              type="button"
              title="查看本轮 trace"
              onClick={() => onOpenTrace(run)}
              className="inline-flex items-center gap-1 rounded-md border border-stone-200 bg-white px-1.5 py-0.5 text-[10.5px] text-stone-500 transition hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600"
            >
              <ListTree className="h-3.5 w-3.5" />
              trace
            </button>
          )}
          <span className="opacity-0 transition group-hover/msg:opacity-100">
            <MessageActions
              msg={toActionMessage(msg)}
              handlers={{
                onEdit: isUser ? startEdit : undefined,
                onRegenerate: role === 'assistant' ? onRegenerate : undefined,
              }}
              hidden={regenPending ? ['regenerate'] : undefined}
            />
          </span>
          {regenPending && role === 'assistant' && (
            <Loader2 className="h-3 w-3 animate-spin text-stone-400" />
          )}
        </div>
      )}
    </div>
  );
};

const KNOWN_ROLES: ReadonlySet<string> = new Set(['user', 'assistant', 'system', 'tool']);

function toActionMessage(m: MessageItem): ChatActionMessage {
  const role: ChatActionRole = KNOWN_ROLES.has(m.role)
    ? (m.role as ChatActionRole)
    : 'assistant';
  return { id: String(m.id), role, content: m.content };
}
