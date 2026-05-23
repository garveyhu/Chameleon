/** Eval Job 详情页 —— 概览 + trend chart + 最近 runs 表
 *
 * 设计：
 *  - Header：返回 / job_key / 立即触发 / 编辑 / 启用切换
 *  - 4 张卡片：cron / dataset / judge / alert
 *  - SVG trend chart：最近 30 次 mean_score
 *  - 表格：runs 列表
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Pencil, Play } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { SectionCard } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import { EvalJobFormModal } from '@/system/eval_jobs/components/eval-job-form-modal';
import { evalJobApi } from '@/system/eval_jobs/services/eval-job';
import type {
  EvalJobRunItem,
  UpdateEvalJobPayload,
} from '@/system/eval_jobs/types/eval-job';

export const EvalJobDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const jobId = id ?? '';
  const qc = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);

  const jobQ = useQuery({
    queryKey: ['eval-job', jobId],
    queryFn: () => evalJobApi.get(jobId),
    enabled: !!jobId,
  });

  const runsQ = useQuery({
    queryKey: ['eval-job-runs', jobId],
    queryFn: () => evalJobApi.listRuns(jobId, 50),
    enabled: !!jobId,
    refetchInterval: 10_000,
  });

  const updateMut = useMutation({
    mutationFn: (payload: UpdateEvalJobPayload) =>
      evalJobApi.update(jobId, payload),
    onSuccess: () => {
      toast.success('已保存');
      qc.invalidateQueries({ queryKey: ['eval-job', jobId] });
      qc.invalidateQueries({ queryKey: ['eval-jobs'] });
      setEditOpen(false);
    },
  });

  const trigMut = useMutation({
    mutationFn: () => evalJobApi.trigger(jobId),
    onSuccess: r => {
      const score =
        r.mean_score !== null ? Number(r.mean_score).toFixed(4) : 'n/a';
      toast.success(`触发完成 · ${r.status} · 分数 ${score}`);
      qc.invalidateQueries({ queryKey: ['eval-job', jobId] });
      qc.invalidateQueries({ queryKey: ['eval-job-runs', jobId] });
    },
    onError: (e: unknown) => {
      toast.error((e as { message?: string })?.message || '触发失败');
    },
  });

  if (!jobId) {
    return (
      <SectionCard>
        <div className="p-6 text-sm text-stone-500">非法的 job id</div>
      </SectionCard>
    );
  }

  const job = jobQ.data;
  const runs = runsQ.data ?? [];

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Link
          to="/eval-jobs"
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> 评测任务
        </Link>
        <span className="text-stone-300">/</span>
        {jobQ.isLoading ? (
          <span className="text-[12.5px] text-stone-400">加载中…</span>
        ) : job ? (
          <>
            <span className="text-[15px] font-medium text-stone-900">
              {job.name}
            </span>
            <span className="font-mono text-[11.5px] text-stone-500">
              {job.job_key}
            </span>
            <Badge
              variant="outline"
              className={cn(
                'text-[10.5px]',
                job.enabled
                  ? 'bg-emerald-50 text-emerald-700'
                  : 'bg-stone-50 text-stone-500',
              )}
            >
              {job.enabled ? '启用' : '禁用'}
            </Badge>
            <span className="ml-auto flex items-center gap-2">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setEditOpen(true)}
              >
                <Pencil className="mr-1 h-3 w-3" /> 编辑
              </Button>
              <Button
                size="sm"
                onClick={() => trigMut.mutate()}
                disabled={!job.enabled || trigMut.isPending}
              >
                <Play className="mr-1 h-3 w-3" />
                {trigMut.isPending ? '触发中…' : '立即触发'}
              </Button>
            </span>
          </>
        ) : (
          <span className="text-[12.5px] text-stone-400">未找到</span>
        )}
      </div>

      {job && <OverviewCards job={job} />}

      <SectionCard className="!p-4">
        <h3 className="mb-3 text-[13px] font-medium text-stone-800">
          mean_score 趋势（最近 {runs.length} 次）
        </h3>
        <TrendChart runs={runs} />
      </SectionCard>

      <SectionCard className="!p-4">
        <h3 className="mb-3 text-[13px] font-medium text-stone-800">
          运行历史
        </h3>
        {runs.length === 0 ? (
          <div className="py-8 text-center text-[12px] text-stone-400">
            还没有运行记录
          </div>
        ) : (
          <RunsTable runs={runs} />
        )}
      </SectionCard>

      <EvalJobFormModal
        open={editOpen}
        initial={job}
        loading={updateMut.isPending}
        onClose={() => setEditOpen(false)}
        onSubmit={p => updateMut.mutate(p as UpdateEvalJobPayload)}
      />
    </div>
  );
};

// ── 概览卡片 ──────────────────────────────────────────

interface JobOverviewCardsProps {
  job: NonNullable<ReturnType<typeof useQuery>['data']> extends never
    ? never
    : import('@/system/eval_jobs/types/eval-job').EvalJobItem;
}

const OverviewCards: React.FC<JobOverviewCardsProps> = ({ job }) => {
  const cards = [
    { label: 'Cron', value: job.cron_expr, mono: true },
    { label: 'Dataset', value: `#${job.dataset_id}`, mono: true },
    { label: 'Judge', value: job.judge },
    { label: 'Target', value: `${job.target_kind} / ${job.target_key ?? '—'}` },
    {
      label: '最近分数',
      value:
        job.last_score !== null ? Number(job.last_score).toFixed(4) : '—',
      mono: true,
    },
    {
      label: '最近触发',
      value: job.last_run_at ? formatDateTime(job.last_run_at) : '—',
      mono: true,
    },
    {
      label: 'Alert',
      value: job.alert_config
        ? `${job.alert_config.kind} · 阈值 ${job.alert_config.regression_threshold ?? 0.1}`
        : '未启用',
    },
    {
      label: 'Updated',
      value: formatDateTime(job.updated_at),
      mono: true,
    },
  ];

  return (
    <div className="grid grid-cols-4 gap-2">
      {cards.map(c => (
        <div
          key={c.label}
          className="rounded-md border border-stone-200/70 bg-white px-3 py-2"
        >
          <div className="text-[10.5px] uppercase tracking-wider text-stone-400">
            {c.label}
          </div>
          <div
            className={cn(
              'mt-0.5 truncate text-[12.5px] text-stone-800',
              c.mono && 'font-mono tnum',
            )}
            title={c.value}
          >
            {c.value}
          </div>
        </div>
      ))}
    </div>
  );
};

// ── trend chart ──────────────────────────────────────

interface TrendChartProps {
  runs: EvalJobRunItem[];
}

const TrendChart: React.FC<TrendChartProps> = ({ runs }) => {
  // runs 是 desc，画图要 asc
  const pts = useMemo(() => {
    return [...runs]
      .reverse()
      .filter(r => r.mean_score !== null)
      .map(r => ({
        id: r.id,
        score: Number(r.mean_score),
        status: r.status,
        alert: r.alert_sent,
      }));
  }, [runs]);

  if (pts.length === 0) {
    return (
      <div className="py-10 text-center text-[12px] text-stone-400">
        暂无评分数据
      </div>
    );
  }

  const W = 720;
  const H = 160;
  const padX = 28;
  const padY = 16;
  const innerW = W - padX * 2;
  const innerH = H - padY * 2;
  const stepX = pts.length > 1 ? innerW / (pts.length - 1) : 0;

  const toY = (s: number) => padY + innerH - s * innerH;
  const linePath = pts
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${padX + i * stepX} ${toY(p.score)}`)
    .join(' ');

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      height={H}
      className="text-stone-400"
    >
      {/* 横向 grid */}
      {[0, 0.25, 0.5, 0.75, 1].map(v => (
        <g key={v}>
          <line
            x1={padX}
            x2={W - padX}
            y1={toY(v)}
            y2={toY(v)}
            stroke="currentColor"
            strokeOpacity={0.15}
            strokeDasharray="2 3"
          />
          <text
            x={padX - 6}
            y={toY(v) + 3}
            fontSize="9"
            textAnchor="end"
            fill="currentColor"
          >
            {v.toFixed(2)}
          </text>
        </g>
      ))}
      {/* 折线 */}
      <path
        d={linePath}
        fill="none"
        stroke="var(--color-primary-500, #2563eb)"
        strokeWidth={1.5}
      />
      {/* 点 */}
      {pts.map((p, i) => {
        const color =
          p.status === 'success'
            ? '#10b981'
            : p.status === 'failed'
              ? '#ef4444'
              : '#a8a29e';
        return (
          <g key={String(p.id)}>
            <circle
              cx={padX + i * stepX}
              cy={toY(p.score)}
              r={3}
              fill={color}
              stroke="white"
              strokeWidth={1}
            />
            {p.alert && (
              <line
                x1={padX + i * stepX}
                x2={padX + i * stepX}
                y1={padY}
                y2={H - padY}
                stroke="#f59e0b"
                strokeOpacity={0.6}
                strokeDasharray="2 2"
              />
            )}
          </g>
        );
      })}
    </svg>
  );
};

// ── runs table ───────────────────────────────────────

interface RunsTableProps {
  runs: EvalJobRunItem[];
}

const RunsTable: React.FC<RunsTableProps> = ({ runs }) => (
  <table className="w-full text-[12px]">
    <thead className="text-[10.5px] uppercase tracking-wider text-stone-500">
      <tr>
        <th className="px-2 py-1.5 text-left">时间</th>
        <th className="px-2 py-1.5 text-left">触发</th>
        <th className="px-2 py-1.5 text-left">状态</th>
        <th className="px-2 py-1.5 text-right">mean_score</th>
        <th className="px-2 py-1.5 text-right">delta</th>
        <th className="px-2 py-1.5 text-left">alert</th>
      </tr>
    </thead>
    <tbody>
      {runs.map(r => {
        const delta = r.delta_score !== null ? Number(r.delta_score) : null;
        const mean = r.mean_score !== null ? Number(r.mean_score) : null;
        return (
          <tr key={String(r.id)} className="border-t border-stone-200/70">
            <td className="px-2 py-1.5 font-mono text-[10.5px] text-stone-500">
              {formatDateTime(r.created_at)}
            </td>
            <td className="px-2 py-1.5 text-stone-600">{r.triggered_by}</td>
            <td className="px-2 py-1.5">
              <Badge
                variant="outline"
                className={cn(
                  'text-[10.5px]',
                  r.status === 'success'
                    ? 'bg-emerald-50 text-emerald-700'
                    : r.status === 'failed'
                      ? 'bg-rose-50 text-rose-700'
                      : 'bg-stone-50 text-stone-600',
                )}
              >
                {r.status}
              </Badge>
            </td>
            <td className="px-2 py-1.5 text-right font-mono tnum text-stone-800">
              {mean !== null ? mean.toFixed(4) : '—'}
            </td>
            <td
              className={cn(
                'px-2 py-1.5 text-right font-mono tnum',
                delta === null
                  ? 'text-stone-400'
                  : delta < 0
                    ? 'text-rose-600'
                    : delta > 0
                      ? 'text-emerald-600'
                      : 'text-stone-600',
              )}
            >
              {delta === null
                ? '—'
                : `${delta >= 0 ? '+' : ''}${delta.toFixed(4)}`}
            </td>
            <td className="px-2 py-1.5">
              {r.alert_sent ? (
                <Badge
                  variant="outline"
                  className="bg-amber-50 text-[10.5px] text-amber-700"
                >
                  sent
                </Badge>
              ) : (
                <span className="text-[10.5px] text-stone-400">—</span>
              )}
            </td>
          </tr>
        );
      })}
    </tbody>
  </table>
);
