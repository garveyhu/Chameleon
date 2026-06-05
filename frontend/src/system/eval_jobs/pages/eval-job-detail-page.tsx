/** 评测任务详情页 —— 概览信息卡 + 分数趋势 + 运行历史 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Pencil, Play } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { DataTable, type DataTableColumn } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { Button } from '@/core/components/ui/button';
import { Card, CardContent } from '@/core/components/ui/card';
import { TimeSeriesChart } from '@/core/components/ui/time-series-chart';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { formatScore, parseScore, scoreColor } from '@/core/lib/score';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { judgeLabel } from '@/system/datasets/utils/judge-meta';
import { EvalJobFormModal } from '@/system/eval_jobs/components/eval-job-form-modal';
import { evalJobApi } from '@/system/eval_jobs/services/eval-job';
import {
  CRON_CUSTOM_SENTINEL,
  CRON_PRESETS,
  type EvalJobItem,
  type EvalJobRunItem,
  type UpdateEvalJobPayload,
} from '@/system/eval_jobs/types/eval-job';
import { useState } from 'react';

const cronLabel = (expr: string): { label: string; mono: boolean } => {
  const p = CRON_PRESETS.find(
    x => x.value === expr && x.value !== CRON_CUSTOM_SENTINEL,
  );
  return p ? { label: p.label, mono: false } : { label: expr, mono: true };
};

const TRIGGER_LABEL: Record<string, string> = {
  cron: '定时',
  manual: '手动',
  api: '接口',
};
const STATUS_LABEL: Record<string, string> = {
  pending: '等待',
  running: '运行中',
  success: '成功',
  failed: '失败',
  cancelled: '已取消',
};
const statusBg = (s: string): string =>
  s === 'success'
    ? 'bg-emerald-50 text-emerald-700'
    : s === 'failed'
      ? 'bg-rose-50 text-rose-700'
      : 'bg-stone-50 text-stone-600';

export const EvalJobDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const jobId = id ?? '';
  const qc = useQueryClient();
  const navigate = useNavigate();
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
      toast.success(`触发完成 · ${r.status} · 分数 ${formatScore(r.mean_score)}`);
      qc.invalidateQueries({ queryKey: ['eval-job', jobId] });
      qc.invalidateQueries({ queryKey: ['eval-job-runs', jobId] });
    },
    onError: (e: unknown) =>
      toast.error((e as { message?: string })?.message || '触发失败'),
  });

  if (!jobId) {
    return <div className="p-6 text-sm text-stone-500">非法的任务编号</div>;
  }

  const job = jobQ.data;
  const runs = runsQ.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Link
          to="/eval-jobs"
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> 定时任务
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
              {job.enabled ? '启用' : '停用'}
            </Badge>
            <span className="ml-auto flex items-center gap-2">
              <Button size="sm" variant="ghost" onClick={() => setEditOpen(true)}>
                <Pencil className="mr-1 h-3 w-3" /> 编辑
              </Button>
              <Button
                size="sm"
                onClick={() => trigMut.mutate()}
                disabled={!job.enabled || trigMut.isPending}
              >
                <Play className="mr-1 h-3 w-3" />
                {trigMut.isPending ? '运行中…' : '立即运行'}
              </Button>
            </span>
          </>
        ) : (
          <span className="text-[12.5px] text-stone-400">未找到</span>
        )}
      </div>

      {job && <InfoGrid job={job} />}

      <Card>
        <CardContent className="pt-5">
          <h3 className="mb-3 text-[13px] font-medium text-stone-800">
            分数趋势（最近 {runs.length} 次）
          </h3>
          <TrendChart runs={runs} />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-5">
          <h3 className="mb-3 text-[13px] font-medium text-stone-800">
            运行历史
          </h3>
          <RunsTable
            runs={runs}
            loading={runsQ.isLoading && !runsQ.data}
            onOpenRun={runId =>
              job &&
              navigate(`/datasets/${job.dataset_id}/runs/${runId}`)
            }
          />
        </CardContent>
      </Card>

      {editOpen && (
        <EvalJobFormModal
          key={job?.id ?? 'edit'}
          open
          initial={job}
          loading={updateMut.isPending}
          onClose={() => setEditOpen(false)}
          onSubmit={p => updateMut.mutate(p as UpdateEvalJobPayload)}
        />
      )}
    </div>
  );
};

const InfoGrid = ({ job }: { job: EvalJobItem }) => {
  const c = cronLabel(job.cron_expr);
  const lastScore = parseScore(job.last_score);
  const cards: { label: string; value: string; mono?: boolean; cls?: string }[] =
    [
      { label: '计划', value: c.label, mono: c.mono },
      {
        label: '数据集',
        value: job.dataset_name ?? `#${job.dataset_id}`,
        mono: !job.dataset_name,
      },
      {
        label: '评分方案',
        value: job.template_id
          ? `模板 · ${job.template_name ?? `#${job.template_id}`}${
              job.template_version_frozen != null
                ? ` v${job.template_version_frozen}`
                : ''
            }`
          : `评分器 · ${judgeLabel(job.judge)}`,
      },
      {
        label: '被测对象',
        value: `${job.target_kind === 'graph' ? '工作流' : '智能体'} / ${job.target_key ?? '—'}`,
      },
      {
        label: '最近分数',
        value: formatScore(job.last_score),
        mono: true,
        cls: scoreColor(lastScore),
      },
      {
        label: '最近运行',
        value: job.last_run_at ? formatDateTime(job.last_run_at) : '—',
        mono: true,
      },
      {
        label: '告警',
        value: job.alert_config
          ? `${job.alert_config.kind === 'slack' ? 'Slack' : 'Webhook'} · 阈值 ${job.alert_config.regression_threshold ?? 0.1}`
          : '未启用',
      },
      { label: '更新时间', value: formatDateTime(job.updated_at), mono: true },
    ];
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {cards.map(card => (
        <div
          key={card.label}
          className="rounded-md border border-stone-200/70 bg-white px-3 py-2"
        >
          <div className="text-[10.5px] text-stone-400">{card.label}</div>
          <div
            className={cn(
              'mt-0.5 truncate text-[12.5px] text-stone-800',
              card.mono && 'font-mono tnum',
              card.cls,
            )}
            title={card.value}
          >
            {card.value}
          </div>
        </div>
      ))}
    </div>
  );
};

const TrendChart = ({ runs }: { runs: EvalJobRunItem[] }) => {
  const points = [...runs]
    .reverse()
    .filter(r => r.mean_score !== null)
    .map(r => ({ ts: r.created_at, score: parseScore(r.mean_score) ?? 0 }));
  return (
    <TimeSeriesChart
      data={points}
      xKey="ts"
      height={180}
      series={[
        { dataKey: 'score', name: '平均分', color: 'var(--color-primary-600)' },
      ]}
      xTickFormatter={ts =>
        new Date(ts).toLocaleDateString('zh-CN', {
          month: '2-digit',
          day: '2-digit',
        })
      }
      labelFormatter={ts => new Date(ts).toLocaleString('zh-CN')}
      empty="暂无评分数据"
    />
  );
};

const RunsTable = ({
  runs,
  loading,
  onOpenRun,
}: {
  runs: EvalJobRunItem[];
  loading: boolean;
  onOpenRun: (runId: EntityId) => void;
}) => {
  const cols: DataTableColumn<EvalJobRunItem>[] = [
    {
      key: 'created_at',
      header: '时间',
      render: r => (
        <span className="font-mono text-[10.5px] text-stone-500">
          {formatDateTime(r.created_at)}
        </span>
      ),
    },
    {
      key: 'triggered_by',
      header: '触发方式',
      width: 90,
      render: r => (
        <span className="text-stone-600">
          {TRIGGER_LABEL[r.triggered_by] ?? r.triggered_by}
        </span>
      ),
    },
    {
      key: 'status',
      header: '状态',
      width: 88,
      render: r => (
        <Badge
          variant="outline"
          className={cn('text-[10.5px]', statusBg(r.status))}
        >
          {STATUS_LABEL[r.status] ?? r.status}
        </Badge>
      ),
    },
    {
      key: 'mean_score',
      header: '平均分',
      align: 'right',
      width: 84,
      render: r => (
        <span className={cn('tnum', scoreColor(parseScore(r.mean_score)))}>
          {formatScore(r.mean_score)}
        </span>
      ),
    },
    {
      key: 'delta_score',
      header: '分数变化',
      align: 'right',
      width: 92,
      render: r => {
        const d = parseScore(r.delta_score);
        if (d === null) return <span className="text-stone-400">—</span>;
        return (
          <span
            className={cn(
              'tnum',
              d < 0
                ? 'text-rose-600'
                : d > 0
                  ? 'text-emerald-600'
                  : 'text-stone-600',
            )}
          >
            {d >= 0 ? '+' : ''}
            {d.toFixed(2)}
          </span>
        );
      },
    },
    {
      key: 'alert_sent',
      header: '告警',
      width: 72,
      render: r =>
        r.alert_sent ? (
          <Badge
            variant="outline"
            className="bg-amber-50 text-[10.5px] text-amber-700"
          >
            已发送
          </Badge>
        ) : (
          <span className="text-[10.5px] text-stone-400">—</span>
        ),
    },
  ];
  return (
    <DataTable
      columns={cols}
      rows={runs}
      rowKey="id"
      loading={loading}
      onRowClick={r => {
        if (r.dataset_run_id != null) onOpenRun(r.dataset_run_id);
      }}
      emptyText="还没有运行记录"
      minWidth={560}
    />
  );
};
