/** 应用详情「会话」tab —— 该应用近期的会话 / 运行
 *
 * 复用会话账本的数据源（callLogApi.list 按 agent_key 过滤）与徽标。展示近 N 条紧凑列表，
 * 顶部给「在会话账本中查看全部」跳 /sessions?agent_key=X。点行开 TraceDrawer 下钻。
 */
import { useState } from 'react';

import { useQuery } from '@tanstack/react-query';
import { ArrowRight, ScrollText } from 'lucide-react';
import { Link } from 'react-router-dom';

import { EmptyState } from '@/core/components/common/empty-state';
import { DataTable, type DataTableColumn } from '@/core/components/table';
import { StatusBadge } from '@/core/components/ui/status-badge';
import { formatCost, formatDateTime, formatDurationMs, formatTokens } from '@/core/lib/format';
import { ChannelLabel, KindBadge } from '@/system/call_logs/components/ledger-badges';
import { TraceDrawer } from '@/system/call_logs/components/trace-drawer';
import { callLogApi } from '@/system/call_logs/services/call-log';
import type { CallLogItem } from '@/system/call_logs/types/call-log';

interface Props {
  agentKey: string;
}

const RECENT_SIZE = 20;

export const AgentSessionsTab = ({ agentKey }: Props) => {
  const [traceLog, setTraceLog] = useState<CallLogItem | null>(null);

  const listQ = useQuery({
    queryKey: ['agent-sessions', agentKey],
    queryFn: () => callLogApi.list({ page: 1, page_size: RECENT_SIZE, agent_key: agentKey }),
    enabled: !!agentKey,
  });

  const rows = listQ.data?.items ?? [];
  const total = listQ.data?.total ?? 0;

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
      key: 'channel',
      header: '渠道',
      width: 92,
      render: l => <ChannelLabel channel={l.channel} />,
    },
    {
      key: 'kind',
      header: '类型',
      width: 96,
      render: l => <KindBadge source={l.source} kind={l.kind} />,
    },
    {
      key: 'status',
      header: '状态',
      width: 96,
      render: l =>
        l.success ? (
          <StatusBadge tone="success">成功</StatusBadge>
        ) : (
          <StatusBadge tone="error">失败 {l.code}</StatusBadge>
        ),
    },
    {
      key: 'tokens',
      header: 'Tokens',
      width: 90,
      align: 'right',
      render: l =>
        l.total_tokens ? (
          <span className="tnum font-mono text-[11.5px] text-stone-700">
            {formatTokens(l.total_tokens)}
          </span>
        ) : (
          <span className="text-stone-400">—</span>
        ),
    },
    {
      key: 'cost',
      header: '成本',
      width: 80,
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
      header: '时延',
      width: 80,
      align: 'right',
      render: l => (
        <span className="tnum font-mono text-[11.5px] text-stone-600">
          {formatDurationMs(l.duration_ms)}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-[12px] text-stone-500">
          近期会话与运行{total > 0 ? ` · 共 ${total} 条` : ''}
        </span>
        <Link
          to={`/sessions?agent_key=${encodeURIComponent(agentKey)}`}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12px] font-medium text-blue-600 transition hover:bg-blue-50"
        >
          在会话账本中查看全部
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>

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
            title="该应用暂无会话与运行记录"
          />
        }
      />

      <TraceDrawer callLog={traceLog} onClose={() => setTraceLog(null)} />
    </div>
  );
};
