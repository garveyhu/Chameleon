/** 会话 & 运行账本 —— 统一收敛对话与运行（trace）的专业账本页
 *
 * 数据源：call_logs trace 根（parent_id IS NULL）。后端 join 推导 source/kind/api_key_name，
 * 前端零额外请求。行下钻统一开 TraceDrawer（树 / 甘特 / payload）；会话型行额外给
 * 「查看对话」直达 conversation-detail。
 */

import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { MessagesSquare, ScrollText } from 'lucide-react';

import { EmptyState } from '@/core/components/common/empty-state';
import {
  DataTable,
  type DataTableColumn,
  SectionCard,
  TablePagination,
  TableToolbar,
} from '@/core/components/table';
import { StatusBadge } from '@/core/components/ui/status-badge';
import { formatCost, formatDateTime, formatDurationMs, formatTokens } from '@/core/lib/format';
import { agentApi } from '@/system/agents/services/agent';
import { ChannelLabel, KindBadge } from '@/system/call_logs/components/ledger-badges';
import { TraceDrawer } from '@/system/call_logs/components/trace-drawer';
import { callLogApi } from '@/system/call_logs/services/call-log';
import type { CallLogItem } from '@/system/call_logs/types/call-log';

/** 延迟色阶：<1s 静默 / <3s 常规 / <10s 黄 / 更久 红 */
const latencyClass = (ms: number): string =>
  ms < 1000
    ? 'text-stone-500'
    : ms < 3000
      ? 'text-stone-700'
      : ms < 10000
        ? 'text-amber-600'
        : 'text-red-600';

/** 时间区间预设 → 起始 ISO（null = 不限） */
const RANGE_PRESETS: { value: string; label: string; hours: number | null }[] = [
  { value: '24h', label: '近 24 小时', hours: 24 },
  { value: '7d', label: '近 7 天', hours: 24 * 7 },
  { value: '30d', label: '近 30 天', hours: 24 * 30 },
  { value: 'all', label: '全部时间', hours: null },
];

const KIND_FILTER_OPTIONS = [
  { value: 'local', label: '代码' },
  { value: 'graph-chatflow', label: '对话编排' },
  { value: 'graph-workflow', label: '流程编排' },
  { value: 'external', label: '外部' },
];

const CHANNEL_FILTER_OPTIONS = [
  { value: 'api', label: 'API' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'embed', label: '嵌入' },
  { value: 'playground', label: 'Playground' },
  { value: 'internal', label: '内部' },
];

/** 会话型判定：有 session_id 且属于对话类（代码 / 对话编排）→ 可直达对话详情 */
const isConversational = (l: CallLogItem): boolean =>
  !!l.session_id &&
  (l.source === 'local' || (l.source === 'graph' && l.kind === 'chatflow'));

export const SessionLedgerPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [range, setRange] = useState('7d');
  // 从应用详情「会话」tab 跳入时携带 agent_key，预选对应应用
  const [agentKey, setAgentKey] = useState(() => searchParams.get('agent_key') ?? 'all');
  const [kind, setKind] = useState('all');
  const [channel, setChannel] = useState('all');
  const [success, setSuccess] = useState('all');
  const [traceLog, setTraceLog] = useState<CallLogItem | null>(null);

  // 智能体下拉：拉一次 agents 列表建选项（kind 由后端在行里给，下拉只筛 agent_key）
  const agentsQ = useQuery({
    queryKey: ['agents', 'ledger-filter'],
    queryFn: () => agentApi.list(),
    staleTime: 60_000,
  });
  const agentOptions = useMemo(
    () => (agentsQ.data ?? []).map(a => ({ value: a.agent_key, label: a.name || a.agent_key })),
    [agentsQ.data],
  );

  const resetPage = () => setPage(1);

  const listQ = useQuery({
    // range 入 key（since 在 fetch 时现算，避免 render 中调 Date.now 副作用）
    queryKey: ['session-ledger', page, pageSize, range, agentKey, kind, channel, success],
    queryFn: () => {
      const def = RANGE_PRESETS.find(p => p.value === range);
      const since = def?.hours
        ? new Date(Date.now() - def.hours * 3600 * 1000).toISOString()
        : undefined;
      return callLogApi.list({
        page,
        page_size: pageSize,
        since,
        agent_key: agentKey === 'all' ? undefined : agentKey,
        channel: channel === 'all' ? undefined : channel,
        success: success === 'all' ? undefined : success === 'true',
      });
    },
  });

  // kind 在后端是 source+kind 派生，无单一列；前端对当前页做客户端过滤
  const rows = useMemo(() => {
    const items = listQ.data?.items ?? [];
    if (kind === 'all') return items;
    return items.filter(l => {
      if (kind === 'local') return l.source === 'local';
      if (kind === 'graph-chatflow') return l.source === 'graph' && l.kind === 'chatflow';
      if (kind === 'graph-workflow') return l.source === 'graph' && l.kind === 'workflow';
      if (kind === 'external')
        return l.source === 'dify' || l.source === 'fastgpt' || l.source === 'coze';
      return true;
    });
  }, [listQ.data?.items, kind]);

  const columns: DataTableColumn<CallLogItem>[] = [
    {
      key: 'created_at',
      header: '时间',
      width: 150,
      render: l => (
        <span className="tnum font-mono text-[11.5px] text-stone-500">
          {formatDateTime(l.created_at)}
        </span>
      ),
    },
    {
      key: 'agent',
      header: '智能体 / 编排',
      render: l => (
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-1.5">
            <span className="truncate font-mono text-[12px] font-medium text-stone-800">
              {l.agent_key}
            </span>
            <KindBadge source={l.source} kind={l.kind} />
            {l.stream && (
              <span className="shrink-0 rounded bg-stone-100 px-1 py-0.5 text-[9.5px] text-stone-500">
                流式
              </span>
            )}
          </div>
          {!l.success && l.error_message && (
            <div className="truncate text-[10.5px] text-red-500" title={l.error_message}>
              {l.error_message}
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'channel',
      header: '渠道',
      width: 92,
      render: l => <ChannelLabel channel={l.channel} />,
    },
    {
      key: 'key',
      header: 'Key / 来源',
      width: 150,
      render: l => (
        <div className="min-w-0">
          <div className="truncate text-[11.5px] text-stone-700">
            {l.api_key_name ?? <span className="text-stone-400">—</span>}
          </div>
          <div className="truncate font-mono text-[10px] text-stone-400">{l.app_id}</div>
        </div>
      ),
    },
    {
      key: 'model',
      header: '模型',
      width: 132,
      render: l =>
        l.model_code ? (
          <span className="truncate font-mono text-[11px] text-stone-600">{l.model_code}</span>
        ) : (
          <span className="text-stone-400">—</span>
        ),
    },
    {
      key: 'status',
      header: t('common.status'),
      width: 100,
      render: l =>
        l.success ? (
          <StatusBadge tone="success">成功</StatusBadge>
        ) : (
          <StatusBadge tone="error">失败 {l.code}</StatusBadge>
        ),
    },
    {
      key: 'tokens',
      header: t('table.tokens'),
      width: 110,
      align: 'right',
      render: l =>
        l.total_tokens ? (
          <div className="text-right">
            <div className="tnum font-mono text-[11.5px] text-stone-700">
              {formatTokens(l.total_tokens)}
            </div>
            {l.prompt_tokens != null && l.completion_tokens != null && (
              <div className="tnum font-mono text-[10px] text-stone-400">
                ↑{formatTokens(l.prompt_tokens)} ↓{formatTokens(l.completion_tokens)}
              </div>
            )}
          </div>
        ) : (
          <span className="text-stone-400">—</span>
        ),
    },
    {
      key: 'cost',
      header: '成本',
      width: 92,
      align: 'right',
      render: l =>
        l.cost_usd != null ? (
          <span className="tnum font-mono text-[11.5px] text-stone-700">
            {formatCost(l.cost_usd)}
          </span>
        ) : (
          <span className="text-stone-400">—</span>
        ),
    },
    {
      key: 'duration',
      header: t('table.duration'),
      width: 88,
      align: 'right',
      render: l => (
        <span className={`tnum font-mono text-[11.5px] ${latencyClass(l.duration_ms)}`}>
          {formatDurationMs(l.duration_ms)}
        </span>
      ),
    },
    {
      key: 'session',
      header: '会话',
      width: 132,
      render: l =>
        l.session_id ? (
          <div className="flex items-center gap-1.5">
            <span
              className="truncate font-mono text-[10.5px] text-stone-500"
              title={l.session_id}
            >
              {l.session_id.slice(0, 8)}…
            </span>
            {isConversational(l) && (
              <button
                type="button"
                title="查看对话"
                className="shrink-0 rounded p-0.5 text-stone-400 transition hover:bg-stone-100 hover:text-blue-600"
                onClick={e => {
                  e.stopPropagation();
                  navigate(`/conversations/${encodeURIComponent(l.session_id as string)}`);
                }}
              >
                <MessagesSquare className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        ) : (
          <span className="text-stone-400">—</span>
        ),
    },
  ];

  return (
    <div>
      <SectionCard>
        <TableToolbar
          title={t('page.session_ledger_title', '会话 & 运行')}
          filters={[
            {
              value: range,
              onChange: v => {
                setRange(v);
                resetPage();
              },
              placeholder: '时间区间',
              allLabel: '全部时间',
              options: RANGE_PRESETS.filter(p => p.value !== 'all'),
              width: 116,
            },
            {
              value: agentKey,
              onChange: v => {
                setAgentKey(v);
                resetPage();
              },
              placeholder: '智能体',
              options: agentOptions,
              width: 150,
            },
            {
              value: kind,
              onChange: v => {
                setKind(v);
                resetPage();
              },
              placeholder: '编排方式',
              options: KIND_FILTER_OPTIONS,
              width: 116,
            },
            {
              value: channel,
              onChange: v => {
                setChannel(v);
                resetPage();
              },
              placeholder: '渠道',
              options: CHANNEL_FILTER_OPTIONS,
              width: 110,
            },
            {
              value: success,
              onChange: v => {
                setSuccess(v);
                resetPage();
              },
              placeholder: t('common.status'),
              options: [
                { value: 'true', label: '仅成功' },
                { value: 'false', label: '仅失败' },
              ],
              width: 100,
            },
          ]}
        />

        <DataTable
          columns={columns}
          rows={rows}
          rowKey="id"
          loading={listQ.isLoading}
          leftBar={l => (l.success ? 'bg-emerald-400' : 'bg-red-400')}
          onRowClick={row => setTraceLog(row)}
          emptyText={
            <EmptyState
              icon={<ScrollText strokeWidth={1.5} />}
              title={t('empty.session_ledger', '暂无会话与运行记录')}
            />
          }
        />

        <TablePagination
          page={page}
          pageSize={pageSize}
          total={listQ.data?.total || 0}
          onPageChange={setPage}
          onPageSizeChange={s => {
            setPageSize(s);
            resetPage();
          }}
        />
      </SectionCard>
      <TraceDrawer
        callLog={traceLog}
        onClose={() => setTraceLog(null)}
        onPrev={() => {
          const i = rows.findIndex(r => r.id === traceLog?.id);
          if (i > 0) setTraceLog(rows[i - 1]);
        }}
        onNext={() => {
          const i = rows.findIndex(r => r.id === traceLog?.id);
          if (i >= 0 && i < rows.length - 1) setTraceLog(rows[i + 1]);
        }}
        hasPrev={!!traceLog && rows.findIndex(r => r.id === traceLog.id) > 0}
        hasNext={
          !!traceLog &&
          rows.findIndex(r => r.id === traceLog.id) < rows.length - 1 &&
          rows.some(r => r.id === traceLog.id)
        }
      />
    </div>
  );
};
