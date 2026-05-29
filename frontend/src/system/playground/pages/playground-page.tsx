/** Playground —— 单聊三栏（默认）/ 对比多列（共享输入广播）两态
 *
 * 单聊：左 预设 · 中 对话流+输入 · 右 运行设置(ParamPanel)。
 * 对比：N 列并排，列头模型名 + 齿轮 popover 改参数；底部共享 composer 一次广播到所有列。
 * 状态全在 core/stores/chat（按 columnId）。
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { KeyRound, Plus, Settings2, Sparkles, Trash2, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import { SectionCard } from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/core/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@/core/components/ui/select';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import { useAuthStore } from '@/core/stores/auth-store';
import { MAX_COLUMNS, isStreaming, useChatStore } from '@/core/stores/chat';
import { selectApiKeyId } from '@/core/stores/chat/selectors';
import { apiKeyApi } from '@/system/api_keys/services/app';
import { callLogApi } from '@/system/call_logs/services/call-log';
import { conversationApi } from '@/system/conversations/services/conversation';
import type { MessageItem } from '@/system/conversations/types/message-tree';
import type { UploadResult } from '@/system/files/services/file-upload';
import type { EntityId } from '@/core/types/api';
import { modelApi } from '@/system/models/services/model';
import { Composer } from '@/system/playground/components/composer';
import { MessageThread } from '@/system/playground/components/message-thread';
import { ParamPanel } from '@/system/playground/components/param-panel';
import type {
  PlaygroundMessage,
  PlaygroundParams,
} from '@/system/playground/types/playground';

/** 后台历史 message → playground 消息流（仅取 user/assistant，标记已完成） */
const toPlaygroundMessages = (msgs: MessageItem[]): PlaygroundMessage[] =>
  msgs
    .filter(m => m.role === 'user' || m.role === 'assistant')
    .map(m => ({
      id: String(m.id),
      role: m.role as 'user' | 'assistant',
      content: m.content,
      status: 'done' as const,
      usage: m.usage
        ? {
            input_tokens: Number(m.usage.input_tokens ?? 0),
            output_tokens: Number(m.usage.output_tokens ?? 0),
            total_tokens: Number(m.usage.total_tokens ?? 0),
          }
        : null,
      requestId: m.request_id ?? undefined,
      feedback: (m.feedback as 1 | -1 | null | undefined) ?? null,
    }));

/** session.meta.config → 部分 PlaygroundParams（resume 时恢复运行设置） */
const metaToParams = (
  meta: Record<string, unknown> | null | undefined,
): Partial<PlaygroundParams> | undefined => {
  const cfg = meta?.config as Record<string, unknown> | undefined;
  if (!cfg) return undefined;
  const num = (v: unknown): number | undefined =>
    typeof v === 'number' ? v : undefined;
  const out: Partial<PlaygroundParams> = {
    system_prompt: typeof cfg.system_prompt === 'string' ? cfg.system_prompt : '',
    temperature: num(cfg.temperature) ?? 0.7,
    top_p: cfg.top_p === null ? null : num(cfg.top_p) ?? 1,
    max_tokens: cfg.max_tokens === null ? null : num(cfg.max_tokens) ?? null,
    // kb_ids 归一成 string（与 KB 下拉一致，雪花 id 安全）
    kb_ids: Array.isArray(cfg.kb_ids) ? cfg.kb_ids.map(String) : [],
    bound_agent_key:
      typeof cfg.bound_agent_key === 'string' ? cfg.bound_agent_key : null,
  };
  // 雪花 id 后端存字符串；仅当存在时写入，避免 undefined 覆盖掉当前模型（老会话存的是数字 → 跳过）
  if (typeof cfg.model_id === 'string') out.model_id = cfg.model_id as EntityId;
  return out;
};

const PRESETS: { label: string; system: string }[] = [
  { label: '＋ 空白对话', system: '' },
  { label: '客服话术调优', system: '你是耐心、专业的客服助手，回答简洁友好，必要时引导用户提供更多信息。' },
  { label: 'SQL 生成器', system: '你是 SQL 专家。根据自然语言需求只输出可执行的 SQL，不要解释。' },
  { label: '中英互译', system: '你是翻译助手：输入中文则翻成地道英文，输入英文则翻成地道中文，只输出译文。' },
];

export const PlaygroundPage = () => {
  const [mode, setMode] = useState<'single' | 'compare'>('single');
  const columns = useChatStore(s => s.columns);
  const addColumn = useChatStore(s => s.addColumn);
  const updateParams = useChatStore(s => s.updateParams);
  const send = useChatStore(s => s.send);
  const stop = useChatStore(s => s.stop);
  const clearMessages = useChatStore(s => s.clearMessages);

  const first = columns[0];

  return (
    <SectionCard className="!p-0">
      <div className="flex items-center gap-3 border-b border-stone-200/70 px-4 py-2.5">
        <h2 className="text-[14px] font-medium text-stone-900">Playground</h2>
        <div className="flex overflow-hidden rounded-lg border border-stone-200 text-[12px]">
          <button
            type="button"
            onClick={() => setMode('single')}
            className={cn('px-3 py-1', mode === 'single' ? 'bg-blue-50 font-medium text-blue-700' : 'text-stone-500')}
          >
            单聊
          </button>
          <button
            type="button"
            onClick={() => setMode('compare')}
            className={cn('px-3 py-1', mode === 'compare' ? 'bg-blue-50 font-medium text-blue-700' : 'text-stone-500')}
          >
            对比
          </button>
        </div>
        <span className="ml-auto" />
        <KeyPicker />
        {mode === 'compare' && (
          <Button size="sm" variant="ghost" onClick={addColumn} disabled={columns.length >= MAX_COLUMNS}>
            <Plus className="mr-1 h-3.5 w-3.5" />
            加列（最多 {MAX_COLUMNS}）
          </Button>
        )}
      </div>

      {mode === 'single' ? (
        <SinglePane
          columnId={first.id}
          onSend={(t, a) => void send(first.id, t, a)}
          onStop={() => stop(first.id)}
          onClear={() => clearMessages(first.id)}
          applyPreset={sys => updateParams(first.id, { ...first.params, system_prompt: sys })}
        />
      ) : (
        <ComparePane
          onBroadcast={(t, a) => columns.forEach(c => void send(c.id, t, a))}
          onStopAll={() => columns.forEach(c => stop(c.id))}
        />
      )}
    </SectionCard>
  );
};

// ── A · 单聊三栏 ──────────────────────────────────────────

const SinglePane = ({
  columnId,
  onSend,
  onStop,
  onClear,
  applyPreset,
}: {
  columnId: string;
  onSend: (t: string, a: UploadResult[]) => void;
  onStop: () => void;
  onClear: () => void;
  applyPreset: (system: string) => void;
}) => {
  const params = useChatStore(s => s.columns.find(c => c.id === columnId)?.params);
  const sessionId = useChatStore(s => s.columns.find(c => c.id === columnId)?.sessionId);
  const updateParams = useChatStore(s => s.updateParams);
  const loadSession = useChatStore(s => s.loadSession);
  const streaming = useChatStore(s => isStreaming(s, columnId));

  const user = useAuthStore(s => s.user);
  const endUser = user ? String(user.id) : undefined;
  const qc = useQueryClient();

  const sessionsQ = useQuery({
    queryKey: ['playground-sessions', endUser],
    queryFn: () =>
      callLogApi.listSessions({
        channel: 'playground',
        end_user_id: endUser,
        page: 1,
        page_size: 50,
      }),
    enabled: !!endUser,
  });

  // 流结束后刷新历史列表（新会话冒泡到顶部）；zustand 读 streaming，invalidate 非 setState
  useEffect(() => {
    if (!streaming && endUser)
      qc.invalidateQueries({ queryKey: ['playground-sessions', endUser] });
  }, [streaming, endUser, qc]);

  const openSession = async (sid: string) => {
    if (sid === sessionId) return;
    try {
      // 并行拉消息 + 会话详情（meta.config 恢复运行设置）
      const [detail, res] = await Promise.all([
        conversationApi.get(sid).catch(() => null),
        conversationApi.listMessages(sid),
      ]);
      loadSession(
        columnId,
        sid,
        toPlaygroundMessages(res.items),
        metaToParams(detail?.meta),
      );
    } catch {
      toast.error('载入会话失败');
    }
  };

  if (!params) return null;
  const sessions = sessionsQ.data?.items ?? [];

  return (
    <div className="flex h-[calc(100vh-150px)]">
      <aside className="flex w-56 shrink-0 flex-col border-r border-stone-200/70 bg-[var(--color-warm-2)]/30">
        <div className="border-b border-stone-200/70 p-2">
          <button
            type="button"
            onClick={onClear}
            className="flex w-full items-center justify-center gap-1.5 rounded-md border border-stone-200 bg-white py-1.5 text-[12px] font-medium text-stone-700 transition hover:border-stone-300 hover:text-stone-900"
          >
            <Plus className="h-3.5 w-3.5" />
            新对话
          </button>
        </div>
        <div className="flex-1 overflow-auto p-1.5">
          <div className="px-1.5 py-1 text-[10.5px] tracking-wide text-stone-400">
            历史会话
          </div>
          {sessions.length === 0 ? (
            <div className="px-1.5 py-3 text-[11.5px] text-stone-400">
              {sessionsQ.isLoading ? '加载中…' : '暂无历史会话'}
            </div>
          ) : (
            sessions.map(s => {
              const active = s.session_id === sessionId;
              return (
                <button
                  key={s.session_id}
                  type="button"
                  onClick={() => void openSession(s.session_id)}
                  className={cn(
                    'mb-0.5 block w-full rounded-md px-2 py-1.5 text-left transition',
                    active
                      ? 'bg-white shadow-sm ring-1 ring-stone-200'
                      : 'hover:bg-white/70',
                  )}
                >
                  <div className="truncate text-[12px] text-stone-700">
                    {s.title || '未命名会话'}
                  </div>
                  <div className="truncate text-[10px] text-stone-400">
                    {formatDateTime(s.last_message_at ?? s.created_at)} · {s.turn_count} 轮
                  </div>
                </button>
              );
            })
          )}
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-stone-200/70 px-3 py-1.5">
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                className="flex items-center gap-1 rounded px-1.5 py-1 text-[12px] text-stone-500 transition hover:bg-stone-100 hover:text-stone-800"
              >
                <Sparkles className="h-3.5 w-3.5" />
                预设
              </button>
            </PopoverTrigger>
            <PopoverContent align="start" className="!w-56 !p-1">
              {PRESETS.map(p => (
                <button
                  key={p.label}
                  type="button"
                  onClick={() => applyPreset(p.system)}
                  className="block w-full truncate rounded-md px-2 py-1.5 text-left text-[12px] text-stone-600 transition hover:bg-stone-100 hover:text-stone-900"
                >
                  {p.label}
                </button>
              ))}
            </PopoverContent>
          </Popover>
          <button
            type="button"
            title="清空当前对话"
            onClick={onClear}
            className="rounded p-1 text-stone-400 transition hover:bg-rose-50 hover:text-rose-600"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
        <MessageThread columnId={columnId} />
        <div className="border-t border-stone-200/70 p-3">
          <Composer onSend={onSend} streaming={streaming} onStop={onStop} />
        </div>
      </main>

      <aside className="w-72 shrink-0 overflow-auto border-l border-stone-200/70 p-4">
        <div className="mb-3 text-[10.5px] tracking-wide text-stone-400">运行设置</div>
        <ParamPanel params={params} onChange={next => updateParams(columnId, next)} />
      </aside>
    </div>
  );
};

// ── C · 对比多列 + 共享输入 ──────────────────────────────

const ComparePane = ({
  onBroadcast,
  onStopAll,
}: {
  onBroadcast: (t: string, a: UploadResult[]) => void;
  onStopAll: () => void;
}) => {
  const columns = useChatStore(s => s.columns);
  const anyStreaming = useChatStore(s => s.columns.some(c => isStreaming(s, c.id)));
  const removeColumn = useChatStore(s => s.removeColumn);
  const clearMessages = useChatStore(s => s.clearMessages);
  const multi = columns.length > 1;

  return (
    <div className="flex h-[calc(100vh-150px)] flex-col">
      <div className="flex min-h-0 flex-1">
        {columns.map((col, i) => (
          <CompareColumn
            key={col.id}
            columnId={col.id}
            index={i}
            onClear={() => clearMessages(col.id)}
            onRemove={multi ? () => removeColumn(col.id) : undefined}
          />
        ))}
      </div>
      <div className="border-t border-stone-200/70 p-3">
        <Composer
          onSend={onBroadcast}
          streaming={anyStreaming}
          onStop={onStopAll}
          placeholder={`一次输入，广播到全部 ${columns.length} 列同时运行… ⌘/Ctrl+Enter`}
        />
      </div>
    </div>
  );
};

const CompareColumn = ({
  columnId,
  index,
  onClear,
  onRemove,
}: {
  columnId: string;
  index: number;
  onClear: () => void;
  onRemove?: () => void;
}) => {
  const params = useChatStore(s => s.columns.find(c => c.id === columnId)?.params);
  const updateParams = useChatStore(s => s.updateParams);
  const modelsQ = useQuery({
    queryKey: ['playground-models'],
    queryFn: () => modelApi.list({ kind: 'chat' }),
    staleTime: 60_000,
  });
  if (!params) return null;
  const modelLabel =
    modelsQ.data?.find(m => String(m.id) === String(params.model_id))?.code ?? '未选模型';

  return (
    <div className="flex min-w-0 flex-1 flex-col border-r border-stone-200/70 last:border-r-0">
      <header className="flex items-center gap-1.5 border-b border-stone-200/70 bg-[var(--color-warm-2)]/30 px-3 py-2">
        <span className="h-4 w-4 shrink-0 rounded bg-gradient-to-br from-violet-500 to-blue-500" />
        <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-stone-800" title={modelLabel}>
          {modelLabel}
          <span className="ml-1 text-[10.5px] font-normal text-stone-400">列 {index + 1}</span>
        </span>
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              title="参数设置"
              className="rounded p-1 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
            >
              <Settings2 className="h-3.5 w-3.5" />
            </button>
          </PopoverTrigger>
          <PopoverContent align="end" className="!w-[280px] !p-3">
            <ParamPanel params={params} onChange={next => updateParams(columnId, next)} />
          </PopoverContent>
        </Popover>
        <button
          type="button"
          title="清空"
          onClick={onClear}
          className="rounded p-1 text-stone-400 transition hover:bg-rose-50 hover:text-rose-600"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
        {onRemove && (
          <button
            type="button"
            title="移除此列"
            onClick={onRemove}
            className="rounded p-1 text-stone-400 transition hover:bg-rose-50 hover:text-rose-600"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </header>
      <MessageThread columnId={columnId} />
    </div>
  );
};

// ── 溯源 Key 选择器（全局一个 Key）──────────────────────────
// 系统理念：模型随便用，但流量必须挂在一个 key 上溯源（key 绑定计费/作用域/会话）。

const KeyPicker = () => {
  const apiKeyId = useChatStore(selectApiKeyId);
  const setApiKeyId = useChatStore(s => s.setApiKeyId);
  const keysQ = useQuery({
    queryKey: ['playground-keys'],
    queryFn: () => apiKeyApi.list({ page: 1, page_size: 100 }),
    staleTime: 60_000,
  });
  const keys = keysQ.data?.items ?? [];
  const firstKeyId = keys[0]?.id ?? null;
  const selected = keys.find(k => String(k.id) === String(apiKeyId));

  // 默认绑首个可用 key（zustand action，非 React setState，不触发 set-state-in-effect）
  useEffect(() => {
    if (apiKeyId == null && firstKeyId != null) setApiKeyId(firstKeyId);
  }, [apiKeyId, firstKeyId, setApiKeyId]);

  return (
    <Select
      value={apiKeyId != null ? String(apiKeyId) : undefined}
      onValueChange={v => setApiKeyId(v)}
    >
      {/* 自渲染 trigger 内容（不用 SelectValue 镜像，避免长 key 名 + 前缀溢出边界） */}
      <SelectTrigger
        className="!h-7 !w-[200px] gap-1.5 text-[12px]"
        title="溯源 Key —— Playground 流量挂在此 Key 上记账/限流/会话归属"
      >
        <KeyRound className="h-3.5 w-3.5 shrink-0 text-stone-400" />
        <span className="min-w-0 flex-1 truncate text-left">
          {selected ? (
            selected.name
          ) : (
            <span className="text-stone-400">
              {keys.length ? '选择溯源 Key' : '暂无可用 Key'}
            </span>
          )}
        </span>
      </SelectTrigger>
      <SelectContent className="!w-[260px]">
        {keys.map(k => (
          <SelectItem key={k.id} value={String(k.id)}>
            <span className="flex w-full items-center gap-2">
              <span className="truncate">{k.name}</span>
              <span className="ml-auto shrink-0 font-mono text-[10px] text-stone-400">
                {k.key_prefix}
              </span>
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
};
