/** 日志视图 —— 该 graph 的历史运行（graph_runs）列表
 *
 * 复用 graphApi.listRuns 的真实运行记录；状态 / 节点数 / 耗时 / 时间 / request_id。
 */
import { useQuery } from '@tanstack/react-query';
import { ScrollText } from 'lucide-react';

import { DataTable } from '@/core/components/table';
import type { DataTableColumn } from '@/core/components/table';
import { StatusBadge } from '@/core/components/ui/status-badge';
import type { StatusTone } from '@/core/components/ui/status-badge';
import { formatDateTime } from '@/core/lib/format';
import type { EntityId } from '@/core/types/api';
import { graphApi } from '@/system/graphs/services/graph';
import type { GraphRunItem } from '@/system/graphs/types/graph';

interface Props {
  graphId: EntityId;
  graphName: string;
}

const STATUS_TONE: Record<string, StatusTone> = {
  success: 'success',
  failed: 'error',
  running: 'running',
  paused: 'warning',
  pending: 'neutral',
  cancelled: 'neutral',
};

const STATUS_LABEL: Record<string, string> = {
  success: '成功',
  failed: '失败',
  running: '运行中',
  paused: '暂停',
  pending: '等待',
  cancelled: '已取消',
};

export const LogsView = ({ graphId }: Props) => {
  const q = useQuery({
    queryKey: ['graph-runs', graphId],
    queryFn: () => graphApi.listRuns(graphId),
  });

  const columns: DataTableColumn<GraphRunItem>[] = [
    {
      key: 'status',
      header: '状态',
      width: 96,
      render: r => (
        <StatusBadge tone={STATUS_TONE[r.status] ?? 'neutral'}>
          {STATUS_LABEL[r.status] ?? r.status}
        </StatusBadge>
      ),
    },
    {
      key: 'nodes',
      header: '节点数',
      width: 80,
      render: r => <span className="text-[12px] text-stone-600">{r.node_count ?? '—'}</span>,
    },
    {
      key: 'duration',
      header: '耗时',
      width: 96,
      render: r => (
        <span className="font-mono text-[11.5px] text-stone-600">
          {r.duration_ms != null ? `${r.duration_ms}ms` : '—'}
        </span>
      ),
    },
    {
      key: 'request_id',
      header: 'request_id',
      render: r => (
        <span className="truncate font-mono text-[10.5px] text-stone-400">{r.request_id}</span>
      ),
    },
    {
      key: 'created_at',
      header: '时间',
      width: 168,
      render: r => (
        <span className="font-mono text-[11px] text-stone-500">{formatDateTime(r.created_at)}</span>
      ),
    },
  ];

  return (
    <div className="h-full overflow-y-auto">
      <div className="px-10 py-8">
        <header className="mb-4 flex items-center gap-2">
          <ScrollText className="h-4 w-4 text-stone-500" />
          <h1 className="text-[16px] font-semibold text-stone-900">运行日志</h1>
          <span className="text-[12px] text-stone-400">最近 {q.data?.length ?? 0} 次执行</span>
        </header>
        <DataTable
          columns={columns}
          rows={q.data ?? []}
          rowKey={r => String(r.id)}
          loading={q.isLoading}
          emptyText="还没有运行记录；在编排页点「运行」跑一次"
        />
      </div>
    </div>
  );
};
