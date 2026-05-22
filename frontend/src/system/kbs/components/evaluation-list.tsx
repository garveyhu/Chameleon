/** 评估批次列表 —— 容器组件（runner + table + chart + detail sheet） */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Plus, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  DataTable,
  type DataTableColumn,
  TablePagination,
} from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import { confirm } from '@/core/lib/confirm';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import { EvaluationCompareChart } from '@/system/kbs/components/evaluation-compare-chart';
import { EvaluationDetailSheet } from '@/system/kbs/components/evaluation-detail-sheet';
import { EvaluationRunner } from '@/system/kbs/components/evaluation-runner';
import { evaluationApi } from '@/system/kbs/services/evaluation';
import type {
  EvaluationListItem,
  EvaluationStatus,
} from '@/system/kbs/types/evaluation';

interface Props {
  kbId: import('@/core/types/api').EntityId;
}

const STATUS_BADGE: Record<EvaluationStatus, { label: string; cls: string }> = {
  pending: { label: '排队中', cls: 'bg-stone-100 text-stone-600' },
  running: { label: '运行中', cls: 'bg-amber-50 text-amber-700' },
  done: { label: '完成', cls: 'bg-emerald-50 text-emerald-700' },
  failed: { label: '失败', cls: 'bg-rose-50 text-rose-700' },
};

export const EvaluationListTab = ({ kbId }: Props) => {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [runnerOpen, setRunnerOpen] = useState(false);
  const [detailId, setDetailId] = useState<import('@/core/types/api').EntityId | null>(null);

  const listQ = useQuery({
    queryKey: ['kb-evaluations', kbId, page, pageSize],
    queryFn: () => evaluationApi.list(kbId, { page, page_size: pageSize }),
  });

  const items = useMemo(
    () => listQ.data?.items ?? [],
    [listQ.data?.items],
  );
  const hasInflight = useMemo(
    () => items.some(e => e.status === 'pending' || e.status === 'running'),
    [items],
  );

  useEffect(() => {
    if (!hasInflight) return;
    const t = setInterval(() => {
      qc.invalidateQueries({ queryKey: ['kb-evaluations', kbId] });
    }, 2000);
    return () => clearInterval(t);
  }, [hasInflight, kbId, qc]);

  const deleteMut = useMutation({
    mutationFn: (evalId: import('@/core/types/api').EntityId) => evaluationApi.delete(kbId, evalId),
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['kb-evaluations', kbId] });
    },
  });

  const columns: DataTableColumn<EvaluationListItem>[] = [
    {
      key: 'name',
      header: '批次名',
      render: e => (
        <span className="font-medium text-stone-900">{e.name}</span>
      ),
    },
    {
      key: 'mode',
      header: '模式',
      width: 100,
      render: e => (
        <span className="font-mono text-[11.5px] text-stone-600">
          {e.recall_mode}
        </span>
      ),
    },
    {
      key: 'top_k',
      header: 'top_k',
      width: 70,
      render: e => (
        <span className="font-mono tnum text-[11.5px] text-stone-600">{e.top_k}</span>
      ),
    },
    {
      key: 'hit5',
      header: 'hit@5',
      width: 80,
      render: e =>
        e.hit_at_5 == null ? (
          <span className="text-stone-300">—</span>
        ) : (
          <span className="font-mono tnum text-[11.5px] text-stone-700">
            {(e.hit_at_5 * 100).toFixed(1)}%
          </span>
        ),
    },
    {
      key: 'mrr',
      header: 'MRR',
      width: 80,
      render: e =>
        e.mrr == null ? (
          <span className="text-stone-300">—</span>
        ) : (
          <span className="font-mono tnum text-[11.5px] text-stone-700">
            {e.mrr.toFixed(3)}
          </span>
        ),
    },
    {
      key: 'p50',
      header: 'p50',
      width: 80,
      render: e =>
        e.latency_p50_ms == null ? (
          <span className="text-stone-300">—</span>
        ) : (
          <span className="font-mono tnum text-[11.5px] text-stone-500">
            {e.latency_p50_ms.toFixed(0)}ms
          </span>
        ),
    },
    {
      key: 'status',
      header: '状态',
      width: 100,
      render: e => <StatusBadge status={e.status} />,
    },
    {
      key: 'created_at',
      header: '创建时间',
      width: 150,
      render: e => (
        <span className="font-mono tnum text-[11.5px] text-stone-500">
          {formatDateTime(e.created_at)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      width: 50,
      align: 'right',
      render: e => (
        <button
          type="button"
          title="删除"
          className="rounded p-1 text-stone-500 hover:bg-rose-50 hover:text-rose-600"
          onClick={async ev => {
            ev.stopPropagation();
            if (
              await confirm({
                title: `删除评估批次 "${e.name}"？`,
                danger: true,
                confirmText: '删除',
              })
            ) {
              deleteMut.mutate(e.id);
            }
          }}
        >
          <Trash2 className="h-3.5 w-3.5" strokeWidth={1.6} />
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-[14px] font-medium text-stone-900">
          评估历史
        </h3>
        <Button onClick={() => setRunnerOpen(true)}>
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          新建评估
        </Button>
      </div>

      <DataTable
        columns={columns}
        rows={items}
        rowKey="id"
        loading={listQ.isLoading}
        emptyText="尚无评估批次"
        onRowClick={e => setDetailId(e.id)}
      />
      <TablePagination
        page={page}
        pageSize={pageSize}
        total={listQ.data?.total ?? 0}
        onPageChange={setPage}
        onPageSizeChange={s => {
          setPageSize(s);
          setPage(1);
        }}
      />

      {items.length >= 2 && (
        <div className="rounded-lg border border-stone-200/70 bg-white p-3">
          <div className="mb-2 text-[12.5px] font-medium text-stone-800">
            趋势对比
          </div>
          <EvaluationCompareChart evals={items} />
        </div>
      )}

      <EvaluationRunner
        open={runnerOpen}
        onClose={() => setRunnerOpen(false)}
        kbId={kbId}
      />
      <EvaluationDetailSheet
        kbId={kbId}
        evalId={detailId}
        onClose={() => setDetailId(null)}
      />
    </div>
  );
};

const StatusBadge = ({ status }: { status: EvaluationStatus }) => {
  const b = STATUS_BADGE[status];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${b.cls}`}
    >
      {status === 'running' && (
        <Loader2 className="h-3 w-3 animate-spin" strokeWidth={2} />
      )}
      {b.label}
    </span>
  );
};
