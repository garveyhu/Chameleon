/** 会话（Threads）列表 —— 按 ChatSession 维度，一行 = 一串多轮对话
 *
 * 与「运行记录 / Trace」（/traces，call_logs 单次运行）区分：这里是会话线程，点行直达
 * 对话回放 /conversations/{session_id}。数据源 GET /v1/admin/sessions。
 */
import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { MessagesSquare } from 'lucide-react';

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
import { formatDateTime } from '@/core/lib/format';
import { ChannelLabel } from '@/system/call_logs/components/ledger-badges';
import { callLogApi } from '@/system/call_logs/services/call-log';
import type { SessionItem } from '@/system/call_logs/types/call-log';

const CHANNEL_FILTER_OPTIONS = [
  { value: 'api', label: 'API' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'embed', label: '嵌入' },
  { value: 'playground', label: 'Playground' },
  { value: 'internal', label: '内部' },
];

/** 默认时间区间：近 7 天（含今天） */
const defaultRange = (): DateRange => {
  const to = new Date();
  to.setHours(23, 59, 59, 999);
  const from = new Date();
  from.setDate(from.getDate() - 6);
  from.setHours(0, 0, 0, 0);
  return { from, to };
};

export const SessionsPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [range, setRange] = useState<DateRange>(defaultRange);
  const [agentKey, setAgentKey] = useState(() => searchParams.get('agent_key') ?? '');
  const [endUser, setEndUser] = useState('');
  const [channel, setChannel] = useState('all');

  const resetPage = () => setPage(1);
  const sinceIso = range.from.toISOString();
  const untilIso = range.to.toISOString();

  const listQ = useQuery({
    queryKey: ['sessions-list', page, pageSize, sinceIso, untilIso, agentKey, endUser, channel],
    queryFn: () =>
      callLogApi.listSessions({
        page,
        page_size: pageSize,
        since: sinceIso,
        until: untilIso,
        agent_key: agentKey || undefined,
        end_user_id: endUser || undefined,
        channel: channel === 'all' ? undefined : channel,
      }),
    placeholderData: keepPreviousData,
  });

  const columns: DataTableColumn<SessionItem>[] = [
    {
      key: 'last',
      header: '最后活跃',
      width: 150,
      render: s => (
        <span className="tnum font-mono text-[11.5px] text-stone-500">
          {formatDateTime(s.last_message_at ?? s.created_at)}
        </span>
      ),
    },
    {
      key: 'session',
      header: '会话',
      render: s => (
        <div className="min-w-0">
          <div className="truncate text-[12.5px] text-stone-800">
            {s.title || <span className="text-stone-400">未命名会话</span>}
          </div>
          <div className="truncate font-mono text-[10.5px] text-stone-400">{s.session_id}</div>
        </div>
      ),
    },
    {
      key: 'agent',
      header: '智能体',
      width: 200,
      render: s => (
        <span className="truncate font-mono text-[11.5px] text-stone-700">{s.agent_key}</span>
      ),
    },
    {
      key: 'channel',
      header: '渠道',
      width: 90,
      render: s => <ChannelLabel channel={s.channel} />,
    },
    {
      key: 'turns',
      header: '轮次',
      width: 80,
      render: s => (
        <span className="tnum inline-flex items-center rounded-md bg-indigo-50 px-1.5 py-0.5 font-mono text-[11px] font-medium text-indigo-600">
          {s.turn_count}
        </span>
      ),
    },
    {
      key: 'end_user',
      header: '终端用户',
      width: 220,
      render: s =>
        s.end_user_id ? (
          <div
            className="truncate font-mono text-[10.5px] text-stone-500"
            title={s.end_user_id}
          >
            {s.end_user_id}
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
          title="会话"
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
              value: channel,
              onChange: v => {
                setChannel(v);
                resetPage();
              },
              placeholder: '渠道',
              options: CHANNEL_FILTER_OPTIONS,
              width: 110,
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
          rows={listQ.data?.items ?? []}
          rowKey="id"
          loading={listQ.isLoading}
          refreshing={listQ.isFetching}
          onRowClick={s => navigate(`/conversations/${encodeURIComponent(s.session_id)}`)}
          emptyText={
            <EmptyState icon={<MessagesSquare strokeWidth={1.5} />} title="暂无会话" />
          }
        />
        <TablePagination
          page={page}
          pageSize={pageSize}
          total={listQ.data?.total || 0}
          onPageChange={setPage}
          onPageSizeChange={s => {
            setPageSize(s);
            setPage(1);
          }}
        />
      </SectionCard>
    </div>
  );
};
