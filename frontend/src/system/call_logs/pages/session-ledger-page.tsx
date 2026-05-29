/** 会话 & 运行账本 —— 统一收敛对话与运行（trace）的专业账本页
 *
 * 数据源：call_logs trace 根（parent_id IS NULL）。后端 join 推导 source/kind/api_key_name，
 * 前端零额外请求。行下钻统一开 TraceDrawer（树 / 甘特 / payload）；会话型行额外给
 * 「查看对话」直达 conversation-detail。
 */

import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { CheckCircle2, MessagesSquare, ScrollText, Timer, XCircle } from 'lucide-react';

import { AgentPicker } from '@/core/components/common/agent-picker';
import { DateRangePicker, type DateRange } from '@/core/components/common/date-range-picker';
import { EmptyState } from '@/core/components/common/empty-state';
import {
  DataTable,
  type DataTableColumn,
  SectionCard,
  TablePagination,
  TableToolbar,
} from '@/core/components/table';
import { Input } from '@/core/components/ui/input';
import { cn } from '@/core/lib/cn';
import { formatCost, formatDateTime, formatDurationMs, formatTokens } from '@/core/lib/format';
import { ChannelLabel, KindBadge } from '@/system/call_logs/components/ledger-badges';
import { TraceDrawer } from '@/system/call_logs/components/trace-drawer';
import { callLogApi } from '@/system/call_logs/services/call-log';
import type { CallLogItem } from '@/system/call_logs/types/call-log';

/** 默认时间区间：近 7 天（含今天） */
const defaultRange = (): DateRange => {
  const to = new Date();
  to.setHours(23, 59, 59, 999);
  const from = new Date();
  from.setDate(from.getDate() - 6);
  from.setHours(0, 0, 0, 0);
  return { from, to };
};

/** 延迟胶囊：色阶分三档（<3s 绿 / <18s 黄 / 更久 红）+ 计时器图标，参考 LangSmith Latency 列 */
const LatencyPill = ({ ms }: { ms: number }) => {
  const tone =
    ms < 3000
      ? 'bg-emerald-50 text-emerald-600'
      : ms < 18000
        ? 'bg-amber-50 text-amber-600'
        : 'bg-rose-50 text-rose-600';
  return (
    <span
      className={cn(
        'tnum inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-mono text-[11px]',
        tone,
      )}
    >
      <Timer className="h-3 w-3" />
      {formatDurationMs(ms)}
    </span>
  );
};

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

/** 会话型判定：有 session_id 且属于对话类（代码 / 对话编排 / Playground）→ 可直达对话详情 */
const isConversational = (l: CallLogItem): boolean =>
  !!l.session_id &&
  (l.channel === 'playground' ||
    l.source === 'local' ||
    (l.source === 'graph' && l.kind === 'chatflow'));

export const SessionLedgerPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [range, setRange] = useState<DateRange>(defaultRange);
  // 从应用详情「会话」tab 跳入时携带 agent_key，预选对应应用（'' = 全部）
  const [agentKey, setAgentKey] = useState(() => searchParams.get('agent_key') ?? '');
  const [kind, setKind] = useState('all');
  const [channel, setChannel] = useState('all');
  const [success, setSuccess] = useState('all');
  const [endUser, setEndUser] = useState('');
  const [traceLog, setTraceLog] = useState<CallLogItem | null>(null);

  const resetPage = () => setPage(1);
  const sinceIso = range.from.toISOString();
  const untilIso = range.to.toISOString();

  const listQ = useQuery({
    queryKey: [
      'session-ledger',
      page,
      pageSize,
      sinceIso,
      untilIso,
      agentKey,
      channel,
      success,
      endUser,
    ],
    queryFn: () =>
      callLogApi.list({
        page,
        page_size: pageSize,
        since: sinceIso,
        until: untilIso,
        agent_key: agentKey || undefined,
        end_user_id: endUser || undefined,
        channel: channel === 'all' ? undefined : channel,
        success: success === 'all' ? undefined : success === 'true',
      }),
    placeholderData: keepPreviousData,
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
      key: 'status',
      header: '',
      width: 44,
      align: 'center',
      render: l =>
        l.success ? (
          <CheckCircle2 className="mx-auto h-4 w-4 text-emerald-500" />
        ) : (
          <span title={`失败 ${l.code}`}>
            <XCircle className="mx-auto h-4 w-4 text-rose-500" />
          </span>
        ),
    },
    {
      key: 'agent',
      header: '智能体 / 编排',
      width: 220,
      render: l => (
        <div className="min-w-0 overflow-hidden">
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
      key: 'session',
      header: '会话',
      width: 200,
      render: l =>
        l.session_id ? (
          <div className="flex min-w-0 items-center gap-1.5">
            <div className="min-w-0">
              <div className="truncate text-[12px] text-stone-800">
                {l.session_title || <span className="text-stone-400">未命名会话</span>}
              </div>
              <div className="truncate font-mono text-[10px] text-stone-400" title={l.session_id}>
                {l.session_id}
              </div>
            </div>
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
    {
      key: 'input',
      header: '输入',
      render: l =>
        l.input_preview ? (
          <span className="line-clamp-2 text-[11.5px] leading-snug break-words text-stone-600">
            {l.input_preview}
          </span>
        ) : (
          <span className="text-stone-400">—</span>
        ),
    },
    {
      key: 'output',
      header: '输出',
      render: l =>
        l.output_preview ? (
          <span className="line-clamp-2 text-[11.5px] leading-snug break-words text-stone-600">
            {l.output_preview}
          </span>
        ) : (
          <span className="text-stone-400">—</span>
        ),
    },
    {
      key: 'duration',
      header: t('table.duration'),
      width: 92,
      render: l => <LatencyPill ms={l.duration_ms} />,
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
      key: 'channel',
      header: '渠道',
      width: 80,
      render: l => <ChannelLabel channel={l.channel} />,
    },
    {
      key: 'tokens',
      header: t('table.tokens'),
      width: 92,
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
      width: 78,
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
      key: 'created_at',
      header: '时间',
      width: 132,
      render: l => (
        <span className="tnum font-mono text-[11.5px] text-stone-500">
          {formatDateTime(l.created_at)}
        </span>
      ),
    },
  ];

  return (
    <div>
      <SectionCard>
        <TableToolbar
          title="Trace"
          onRefresh={() => listQ.refetch()}
          leadingExtra={
            <>
              <DateRangePicker
                value={range}
                onChange={v => {
                  setRange(v);
                  resetPage();
                }}
              />
              <AgentPicker
                value={agentKey}
                onChange={v => {
                  setAgentKey(v);
                  resetPage();
                }}
              />
            </>
          }
          filters={[
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
                { value: 'true', label: '成功' },
                { value: 'false', label: '失败' },
              ],
              width: 100,
            },
          ]}
          extra={
            <Input
              className="!h-7 text-[12px]"
              style={{ width: 168 }}
              placeholder="终端用户 ID"
              value={endUser}
              onChange={e => setEndUser(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') resetPage();
              }}
            />
          }
        />

        <DataTable
          columns={columns}
          rows={rows}
          rowKey="id"
          minWidth={1400}
          loading={listQ.isLoading}
          refreshing={listQ.isFetching}
          onRowClick={row => setTraceLog(row)}
          rowClassName={row =>
            traceLog && row.id === traceLog.id
              ? 'bg-blue-50/70 hover:bg-blue-50/70'
              : undefined
          }
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
