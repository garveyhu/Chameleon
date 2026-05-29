/** 会话（Threads）列表 —— 按 ChatSession 维度，一行 = 一串多轮对话
 *
 * 与「运行记录 / Trace」（/traces，call_logs 单次运行）区分：这里是会话线程，点行直达
 * 对话回放 /conversations/{session_id}。数据源 GET /v1/admin/sessions。
 */
import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { useQuery } from '@tanstack/react-query';
import { MessagesSquare } from 'lucide-react';

import { EmptyState } from '@/core/components/common/empty-state';
import {
  DataTable,
  type DataTableColumn,
  SectionCard,
  TablePagination,
  TableToolbar,
} from '@/core/components/table';
import { formatDateTime } from '@/core/lib/format';
import { agentApi } from '@/system/agents/services/agent';
import { callLogApi } from '@/system/call_logs/services/call-log';
import type { SessionItem } from '@/system/call_logs/types/call-log';

const RANGE_PRESETS: { value: string; label: string; hours: number | null }[] = [
  { value: '24h', label: '近 24 小时', hours: 24 },
  { value: '7d', label: '近 7 天', hours: 24 * 7 },
  { value: '30d', label: '近 30 天', hours: 24 * 30 },
  { value: 'all', label: '全部时间', hours: null },
];

export const SessionsPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [range, setRange] = useState('7d');
  const [agentKey, setAgentKey] = useState(() => searchParams.get('agent_key') ?? 'all');

  const agentsQ = useQuery({
    queryKey: ['agents', 'sessions-filter'],
    queryFn: () => agentApi.list(),
    staleTime: 60_000,
  });
  const agentOptions = useMemo(
    () => (agentsQ.data ?? []).map(a => ({ value: a.agent_key, label: a.name || a.agent_key })),
    [agentsQ.data],
  );

  const listQ = useQuery({
    queryKey: ['sessions-list', page, pageSize, range, agentKey],
    queryFn: () => {
      const def = RANGE_PRESETS.find(p => p.value === range);
      const since = def?.hours
        ? new Date(Date.now() - def.hours * 3600 * 1000).toISOString()
        : undefined;
      return callLogApi.listSessions({
        page,
        page_size: pageSize,
        since,
        agent_key: agentKey === 'all' ? undefined : agentKey,
      });
    },
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
      width: 180,
      render: s => (
        <span className="truncate font-mono text-[11.5px] text-stone-700">{s.agent_key}</span>
      ),
    },
    {
      key: 'end_user',
      header: '终端用户',
      width: 180,
      render: s =>
        s.end_user_id ? (
          <span className="truncate font-mono text-[10.5px] text-stone-500" title={s.end_user_id}>
            {s.end_user_id}
          </span>
        ) : (
          <span className="text-stone-400">—</span>
        ),
    },
    {
      key: 'turns',
      header: '轮次',
      width: 72,
      align: 'right',
      render: s => (
        <span className="tnum font-mono text-[11.5px] text-stone-700">{s.turn_count}</span>
      ),
    },
  ];

  return (
    <div>
      <SectionCard>
        <TableToolbar
          title="会话"
          filters={[
            {
              value: range,
              onChange: v => {
                setRange(v);
                setPage(1);
              },
              placeholder: '时间区间',
              options: RANGE_PRESETS.filter(p => p.value !== 'all'),
              width: 116,
            },
            {
              value: agentKey,
              onChange: v => {
                setAgentKey(v);
                setPage(1);
              },
              placeholder: '智能体',
              options: agentOptions,
              width: 150,
            },
          ]}
        />
        <DataTable
          columns={columns}
          rows={listQ.data?.items ?? []}
          rowKey="id"
          loading={listQ.isLoading}
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
