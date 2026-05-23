/** Eval Jobs 列表页 —— 列表 + 新建 + 启用/禁用 + 手动 trigger */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FlaskConical, Play, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { SectionCard } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { cn } from '@/core/lib/cn';
import { confirm } from '@/core/lib/confirm';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import { EvalJobFormModal } from '@/system/eval_jobs/components/eval-job-form-modal';
import { evalJobApi } from '@/system/eval_jobs/services/eval-job';
import type {
  CreateEvalJobPayload,
  UpdateEvalJobPayload,
} from '@/system/eval_jobs/types/eval-job';

export const EvalJobsPage = () => {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);

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
    mutationFn: (args: { id: string | number; payload: UpdateEvalJobPayload }) =>
      evalJobApi.update(args.id, args.payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['eval-jobs'] });
    },
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
      const score =
        r.mean_score !== null ? Number(r.mean_score).toFixed(4) : 'n/a';
      toast.success(`触发完成 · ${r.status} · 分数 ${score}`);
      qc.invalidateQueries({ queryKey: ['eval-jobs'] });
    },
    onError: (e: unknown) => {
      const msg = (e as { message?: string })?.message || '触发失败';
      toast.error(msg);
    },
  });

  return (
    <SectionCard>
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="flex items-center gap-1.5 text-[14px] font-medium text-stone-900">
            <FlaskConical className="h-4 w-4 text-stone-500" />
            评测任务
          </h2>
          <p className="mt-0.5 text-[11.5px] text-stone-500">
            把 dataset × judge × cron 打包成可周期触发的 Eval CI；
            分数回归 → 自动 Slack / Webhook 告警
          </p>
        </div>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1 h-3 w-3" />
          新建评测任务
        </Button>
      </header>

      {listQ.isLoading ? (
        <div className="py-12 text-center text-[12px] text-stone-400">
          加载中…
        </div>
      ) : !listQ.data?.length ? (
        <div className="py-12 text-center text-[12px] text-stone-400">
          还没有任务；点右上"新建"开始
        </div>
      ) : (
        <table className="w-full text-[12.5px]">
          <thead className="text-[11px] uppercase tracking-wider text-stone-500">
            <tr>
              <th className="px-2 py-2 text-left">job_key</th>
              <th className="px-2 py-2 text-left">名称</th>
              <th className="px-2 py-2 text-left">Cron</th>
              <th className="px-2 py-2 text-left">最近分数</th>
              <th className="px-2 py-2 text-left">最近触发</th>
              <th className="px-2 py-2 text-left">状态</th>
              <th className="px-2 py-2 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {listQ.data.map(j => (
              <tr
                key={j.id}
                className={cn(
                  'cursor-pointer border-t border-stone-200/70 hover:bg-stone-50',
                )}
                onClick={() => nav(`/eval-jobs/${j.id}`)}
              >
                <td className="px-2 py-2 font-mono text-[11.5px]">
                  {j.job_key}
                </td>
                <td className="px-2 py-2 text-stone-800">{j.name}</td>
                <td className="px-2 py-2 font-mono text-[11px] text-stone-600">
                  {j.cron_expr}
                </td>
                <td className="px-2 py-2 font-mono text-[11.5px] tnum text-stone-700">
                  {j.last_score !== null
                    ? Number(j.last_score).toFixed(4)
                    : '—'}
                </td>
                <td className="px-2 py-2 font-mono text-[11px] text-stone-500">
                  {j.last_run_at ? formatDateTime(j.last_run_at) : '—'}
                </td>
                <td className="px-2 py-2">
                  <Badge
                    variant="outline"
                    className={cn(
                      'text-[10.5px]',
                      j.enabled
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-stone-50 text-stone-500',
                    )}
                  >
                    {j.enabled ? '启用' : '禁用'}
                  </Badge>
                  {j.alert_config && (
                    <Badge
                      variant="outline"
                      className="ml-1 bg-amber-50 text-[10.5px] text-amber-700"
                    >
                      alert
                    </Badge>
                  )}
                </td>
                <td className="px-2 py-2 text-right">
                  <div className="flex items-center justify-end gap-1">
                    <button
                      type="button"
                      title="立即触发一次"
                      disabled={!j.enabled || trigMut.isPending}
                      onClick={e => {
                        e.stopPropagation();
                        trigMut.mutate(j.id);
                      }}
                      className="rounded p-1 text-stone-400 hover:bg-primary-50 hover:text-primary-700 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      <Play className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      title={j.enabled ? '禁用 cron' : '启用 cron'}
                      onClick={e => {
                        e.stopPropagation();
                        updateMut.mutate({
                          id: j.id,
                          payload: { enabled: !j.enabled },
                        });
                      }}
                      className={cn(
                        'rounded px-2 py-1 text-[10.5px] font-medium',
                        j.enabled
                          ? 'bg-stone-50 text-stone-600 hover:bg-stone-200'
                          : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100',
                      )}
                    >
                      {j.enabled ? 'OFF' : 'ON'}
                    </button>
                    <button
                      type="button"
                      title="删除"
                      onClick={async e => {
                        e.stopPropagation();
                        if (
                          await confirm({
                            title: '确认删除？',
                            description: `任务 ${j.job_key} 将被删除；历史 eval_job_runs 一并清理。`,
                          })
                        ) {
                          delMut.mutate(j.id);
                        }
                      }}
                      className="rounded p-1 text-stone-400 hover:bg-rose-50 hover:text-rose-600"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <EvalJobFormModal
        open={createOpen}
        loading={createMut.isPending}
        onClose={() => setCreateOpen(false)}
        onSubmit={p => createMut.mutate(p as CreateEvalJobPayload)}
      />
    </SectionCard>
  );
};
