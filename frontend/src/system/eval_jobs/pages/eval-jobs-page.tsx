/** 评测任务列表页 —— DataTable + 新建 + 启停 + 手动触发 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FlaskConical, Play, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { DataTable, type DataTableColumn } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { cn } from '@/core/lib/cn';
import { confirm } from '@/core/lib/confirm';
import { formatDateTime } from '@/core/lib/format';
import { formatScore, parseScore, scoreColor } from '@/core/lib/score';
import { toast } from '@/core/lib/toast';
import { EvalJobFormModal } from '@/system/eval_jobs/components/eval-job-form-modal';
import { evalJobApi } from '@/system/eval_jobs/services/eval-job';
import {
  CRON_CUSTOM_SENTINEL,
  CRON_PRESETS,
  type CreateEvalJobPayload,
  type EvalJobItem,
  type UpdateEvalJobPayload,
} from '@/system/eval_jobs/types/eval-job';

const cronLabel = (expr: string): { label: string; mono: boolean } => {
  const p = CRON_PRESETS.find(
    x => x.value === expr && x.value !== CRON_CUSTOM_SENTINEL,
  );
  return p ? { label: p.label, mono: false } : { label: expr, mono: true };
};

export const EvalJobsPage = () => {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [sortKey, setSortKey] = useState('last_score');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  const listQ = useQuery({
    queryKey: ['eval-jobs'],
    queryFn: () => evalJobApi.list(),
  });

  const createMut = useMutation({
    mutationFn: (p: CreateEvalJobPayload) => evalJobApi.create(p),
    onSuccess: () => {
      toast.success('已创建');
      qc.invalidateQueries({ queryKey: ['eval-jobs'] });
      setCreateOpen(false);
    },
  });

  const updateMut = useMutation({
    mutationFn: (args: {
      id: string | number;
      payload: UpdateEvalJobPayload;
    }) => evalJobApi.update(args.id, args.payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['eval-jobs'] }),
  });

  const delMut = useMutation({
    mutationFn: (id: string | number) => evalJobApi.delete(id),
    onSuccess: () => {
      toast.success('已删除');
      qc.invalidateQueries({ queryKey: ['eval-jobs'] });
    },
  });

  const trigMut = useMutation({
    mutationFn: (id: string | number) => evalJobApi.trigger(id),
    onSuccess: r => {
      toast.success(`触发完成 · ${r.status} · 分数 ${formatScore(r.mean_score)}`);
      qc.invalidateQueries({ queryKey: ['eval-jobs'] });
    },
    onError: (e: unknown) =>
      toast.error((e as { message?: string })?.message || '触发失败'),
  });

  const cols: DataTableColumn<EvalJobItem>[] = [
    {
      key: 'name',
      header: '任务',
      render: r => (
        <div className="min-w-0">
          <div className="truncate text-stone-800">{r.name}</div>
          <div className="truncate font-mono text-[10.5px] text-stone-400">
            {r.job_key}
          </div>
        </div>
      ),
    },
    {
      key: 'cron',
      header: '计划',
      width: 150,
      render: r => {
        const c = cronLabel(r.cron_expr);
        return (
          <span
            className={cn(
              c.mono ? 'font-mono text-[11px] text-stone-500' : 'text-stone-600',
            )}
          >
            {c.label}
          </span>
        );
      },
    },
    {
      key: 'last_score',
      header: '最近分数',
      align: 'right',
      width: 92,
      sortable: true,
      render: r => (
        <span className={cn('tnum', scoreColor(parseScore(r.last_score)))}>
          {formatScore(r.last_score)}
        </span>
      ),
    },
    {
      key: 'last_run_at',
      header: '最近运行',
      align: 'right',
      width: 150,
      render: r => (
        <span className="text-[11px] text-stone-500">
          {r.last_run_at ? formatDateTime(r.last_run_at) : '—'}
        </span>
      ),
    },
    {
      key: 'status',
      header: '状态',
      width: 108,
      render: r => (
        <div className="flex items-center gap-1">
          <Badge
            variant="outline"
            className={cn(
              'text-[10.5px]',
              r.enabled
                ? 'bg-emerald-50 text-emerald-700'
                : 'bg-stone-50 text-stone-500',
            )}
          >
            {r.enabled ? '启用' : '停用'}
          </Badge>
          {r.alert_config && (
            <Badge
              variant="outline"
              className="bg-amber-50 text-[10.5px] text-amber-700"
            >
              告警
            </Badge>
          )}
        </div>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      width: 132,
      render: r => (
        <div
          className="flex items-center justify-end gap-1"
          onClick={e => e.stopPropagation()}
        >
          <button
            type="button"
            title="立即运行一次"
            disabled={!r.enabled || trigMut.isPending}
            onClick={() => trigMut.mutate(r.id)}
            className="hover:bg-primary-50 hover:text-primary-700 rounded p-1 text-stone-400 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Play className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            title={r.enabled ? '停用定时' : '启用定时'}
            onClick={() =>
              updateMut.mutate({ id: r.id, payload: { enabled: !r.enabled } })
            }
            className={cn(
              'rounded px-2 py-1 text-[10.5px] font-medium',
              r.enabled
                ? 'bg-stone-50 text-stone-600 hover:bg-stone-200'
                : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100',
            )}
          >
            {r.enabled ? '停用' : '启用'}
          </button>
          <button
            type="button"
            title="删除"
            onClick={async () => {
              if (
                await confirm({
                  title: '删除该评测任务？',
                  description: `任务「${r.name}」及其全部历史运行记录将被清除，不可恢复。`,
                  confirmText: '删除',
                  danger: true,
                })
              ) {
                delMut.mutate(r.id);
              }
            }}
            className="rounded p-1 text-stone-400 hover:bg-rose-50 hover:text-rose-600"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ),
    },
  ];

  const rows = [...(listQ.data ?? [])].sort((a, b) => {
    if (sortKey === 'last_score') {
      const va = parseScore(a.last_score) ?? -1;
      const vb = parseScore(b.last_score) ?? -1;
      return sortOrder === 'asc' ? va - vb : vb - va;
    }
    return 0;
  });

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-1.5 text-[14px] font-medium text-stone-900">
            <FlaskConical className="h-4 w-4 text-stone-500" />
            评测任务
          </h1>
          <p className="mt-0.5 text-[11.5px] text-stone-500">
            按计划自动跑数据集评测，分数明显回退时通知你
          </p>
        </div>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1 h-3 w-3" />
          新建评测任务
        </Button>
      </div>

      <DataTable
        columns={cols}
        rows={rows}
        rowKey="id"
        leftBar={r => (r.enabled ? 'bg-emerald-400' : 'bg-stone-300')}
        sortKey={sortKey}
        sortOrder={sortOrder}
        onSortChange={(k, o) => {
          setSortKey(k);
          setSortOrder(o);
        }}
        loading={listQ.isLoading}
        onRowClick={r => nav(`/eval-jobs/${r.id}`)}
        emptyText="还没有评测任务"
        emptyExtra={
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setCreateOpen(true)}
          >
            新建评测任务
          </Button>
        }
      />

      <EvalJobFormModal
        open={createOpen}
        loading={createMut.isPending}
        onClose={() => setCreateOpen(false)}
        onSubmit={p => createMut.mutate(p as CreateEvalJobPayload)}
      />
    </div>
  );
};
