/** 运行对比统计可视化 —— recharts 图表（能力雷达 / 分数分布 / 逐题得分 / 逐样本胜负）
 *  + AI 总结分析（走 aikit 后端，markdown 渲染）。被 RunCompareMatrix 的「对比统计」折叠区复用。 */

import { useMutation, useQuery } from '@tanstack/react-query';
import { Copy, Sparkles } from 'lucide-react';
import { useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { Markdown } from '@/core/components/chat/markdown';
import { NeonLoader } from '@/core/components/ui/neon-loader';
import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import { aiTaskApi } from '@/core/services/ai-task';
import type { AiTaskItem } from '@/core/types/ai-task';
import type { EntityId } from '@/core/types/api';
import type {
  CategoryDef,
  CompareItemCell,
  DatasetRunRow,
} from '@/system/datasets/types/dataset';
import { shortRunName } from '@/system/datasets/utils/run-name';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#f43f5e', '#06b6d4'];

const runMean = (r: DatasetRunRow): number | null => {
  const s = r.summary as Record<string, unknown> | null;
  const v = s?.mean_score ?? s?.mean ?? s?.avg_score;
  return typeof v === 'number' ? v : null;
};

// 分数 5 档（归一分四舍五入到最近 0.25 → 1-5 档）。
const LEVELS = [
  { key: 1, label: '优秀' },
  { key: 0.75, label: '良好' },
  { key: 0.5, label: '及格' },
  { key: 0.25, label: '较差' },
  { key: 0, label: '差' },
];
const bucketKey = (s: number): number => Math.round(s * 4) / 4;

interface Props {
  runs: DatasetRunRow[];
  rows: CompareItemCell[];
  runIds: EntityId[];
  /** 数据集配置的能力维度（雷达的轴）；空 = 未配置 → 不显示雷达 */
  categories?: CategoryDef[] | null;
  /** 导出截图态：展开 AI 分析全文（去掉滚动裁剪）+ 隐藏交互按钮 */
  exporting?: boolean;
}

export const RunCompareStats = ({
  runs,
  rows,
  runIds,
  categories,
  exporting = false,
}: Props) => {
  const cellScore = (row: CompareItemCell, runId: string): number | null => {
    const s = row.cells[runId]?.score;
    return typeof s === 'number' ? s : null;
  };

  // ① 能力雷达：按数据集配置的能力维度（轴）+ 样本 category 归类，各维度每模型平均分。
  // 维度来自后端配置，样本归类由 AI 扩样/手动选/AI 批量回填得到——不再前端关键词猜测。
  const hasCategorized = rows.some(r => !!r.category);
  const radarData = (categories ?? []).map(cat => {
    const point: Record<string, unknown> = { capability: cat.label };
    for (const run of runs) {
      const rid = String(run.id);
      const vals = rows
        .filter(r => r.category === cat.key)
        .map(r => cellScore(r, rid))
        .filter((v): v is number => v != null);
      point[run.name] = vals.length
        ? Number((vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(3))
        : 0;
    }
    return point;
  });

  // ② 分数分布：5 档 × 各模型计数
  const distData = LEVELS.map(lv => {
    const point: Record<string, unknown> = { level: lv.label };
    for (const run of runs) {
      const rid = String(run.id);
      point[run.name] = rows.filter(r => {
        const s = cellScore(r, rid);
        return s != null && bucketKey(s) === lv.key;
      }).length;
    }
    return point;
  });

  // ③ 逐题得分：样本序号 × 各模型分（折线）
  const lineData = rows.map((row, i) => {
    const point: Record<string, unknown> = {
      idx: i + 1,
      q: row.input_preview ?? '',
    };
    for (const run of runs) point[run.name] = cellScore(row, String(run.id));
    return point;
  });

  // ④ 逐样本胜负（以第一个 run 为基准）
  const baseId = runs.length ? String(runs[0].id) : '';
  const winloss = runs.slice(1).map(run => {
    const rid = String(run.id);
    let win = 0;
    let tie = 0;
    let loss = 0;
    for (const row of rows) {
      const a = cellScore(row, rid);
      const b = cellScore(row, baseId);
      if (a == null || b == null) continue;
      if (a > b) win += 1;
      else if (a < b) loss += 1;
      else tie += 1;
    }
    return { run, win, tie, loss };
  });

  // AI 总结分析走 ai_tasks 异步子系统：提交即返、轮询状态、结果缓存 + 离开页面回来反显。
  const scopeRef = [...runIds].map(String).sort().join(',');
  const listQ = useQuery({
    queryKey: ['ai-task:compare', scopeRef],
    queryFn: () =>
      aiTaskApi.list({
        scope: 'run_compare',
        scope_ref: scopeRef,
        task_type: 'eval.compare_analysis',
        limit: 1,
      }),
  });
  const [taskId, setTaskId] = useState<EntityId | null>(null);
  const taskQ = useQuery({
    queryKey: ['ai-task', taskId],
    queryFn: () => aiTaskApi.get(taskId as EntityId),
    enabled: taskId != null,
    // pending/running 时每 2s 轮询，终态停止
    refetchInterval: query => {
      const st = (query.state.data as AiTaskItem | undefined)?.status;
      return st === 'pending' || st === 'running' ? 2000 : false;
    },
  });
  const submitMut = useMutation({
    mutationFn: (force: boolean) =>
      aiTaskApi.submit({
        task_type: 'eval.compare_analysis',
        scope: 'run_compare',
        scope_ref: scopeRef,
        input: { run_ids: runIds.map(String) },
        force,
      }),
    onSuccess: t => setTaskId(t.id),
    onError: (e: unknown) =>
      toast.error((e as { message?: string })?.message || 'AI 分析失败'),
  });

  // 展示态：优先当前轮询任务；未点生成时回退到缓存命中的历史 success 任务
  const activeTask: AiTaskItem | null =
    taskQ.data ??
    (taskId == null
      ? (listQ.data?.find(t => t.status === 'success') ?? null)
      : null);
  const analysisText = (
    activeTask?.result as { analysis?: string } | undefined
  )?.analysis;
  const analyzing =
    submitMut.isPending ||
    activeTask?.status === 'pending' ||
    activeTask?.status === 'running';

  return (
    <div className="space-y-5">
      {/* AI 总结分析 —— 导出图片时整块省略（长 markdown 栅格化极慢，且文字不适合做图）；
          要分享文字用面板内「复制」按钮 */}
      {!exporting && (
      <div className="rounded-lg border border-violet-200/70 bg-violet-50/30 p-3">
        <div className="flex items-center justify-between">
          <span className="text-[12px] font-medium text-violet-800">
            AI 总结分析
          </span>
          <div className="flex items-center gap-2">
          {analysisText && (
            <button
              type="button"
              onClick={() => {
                void navigator.clipboard.writeText(analysisText);
                toast.success('已复制分析全文');
              }}
              className="inline-flex items-center gap-1 rounded-md border border-violet-200 bg-white px-2 py-1 text-[11.5px] font-medium text-violet-700 transition hover:border-violet-300"
            >
              <Copy className="h-3.5 w-3.5" />
              复制
            </button>
          )}
          <button
            type="button"
            disabled={analyzing}
            onClick={() => submitMut.mutate(!!analysisText)}
            className="inline-flex items-center gap-1 rounded-md bg-violet-600 px-2.5 py-1 text-[11.5px] font-medium text-white transition hover:bg-violet-700 disabled:opacity-60"
          >
            {analyzing ? (
              <NeonLoader size="xs" />
            ) : (
              <Sparkles className="h-3.5 w-3.5" />
            )}
            {analyzing ? '分析中…' : analysisText ? '重新分析' : '生成 AI 分析'}
          </button>
          </div>
        </div>
        {analysisText ? (
          <div className="mt-2 max-h-[420px] overflow-auto rounded-md bg-white px-3 py-2 text-[12.5px] leading-relaxed text-stone-700">
            <Markdown content={analysisText} />
          </div>
        ) : activeTask?.status === 'failed' ? (
          <p className="mt-1.5 text-[10.5px] leading-snug text-rose-600">
            分析失败：{activeTask.error ?? '请重试'}
          </p>
        ) : analyzing ? (
          <div className="mt-2">
            <NeonLoader size="sm" label="大模型分析中，异步执行，可离开页面…" />
          </div>
        ) : (
          <p className="mt-1.5 text-[10.5px] leading-snug text-violet-500/80">
            让大模型综合各模型逐题表现，给出排名、强弱项、共性难点与选型建议。结果会缓存，离开页面回来仍可查看。
          </p>
        )}
      </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* 能力雷达 */}
        {radarData.length >= 3 && hasCategorized && (
          <ChartCard title="能力雷达" hint="按数据集能力维度归类，各维度平均分">
            <ResponsiveContainer width="100%" height={260}>
              <RadarChart data={radarData} outerRadius="72%">
                <PolarGrid stroke="#e7e5e4" />
                <PolarAngleAxis
                  dataKey="capability"
                  tick={{ fontSize: 11, fill: '#78716c' }}
                />
                <PolarRadiusAxis domain={[0, 1]} tick={{ fontSize: 9 }} />
                {runs.map((run, i) => (
                  <Radar
                    key={String(run.id)}
                    name={shortRunName(run.name)}
                    dataKey={run.name}
                    stroke={COLORS[i % COLORS.length]}
                    fill={COLORS[i % COLORS.length]}
                    fillOpacity={0.12}
                    isAnimationActive={false}
                  />
                ))}
                <Legend wrapperStyle={{ fontSize: 10 }} />
                <Tooltip formatter={(v: number) => v.toFixed(2)} />
              </RadarChart>
            </ResponsiveContainer>
          </ChartCard>
        )}

        {/* 分数分布 */}
        <ChartCard title="分数分布" hint="各档位（优秀→差）的题数">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={distData} margin={{ top: 8, right: 8, bottom: 4, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f5f5f4" />
              <XAxis dataKey="level" tick={{ fontSize: 11, fill: '#78716c' }} />
              <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: '#a8a29e' }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              {runs.map((run, i) => (
                <Bar
                  key={String(run.id)}
                  name={shortRunName(run.name)}
                  dataKey={run.name}
                  fill={COLORS[i % COLORS.length]}
                  radius={[2, 2, 0, 0]}
                  isAnimationActive={false}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 逐题得分折线 */}
        <ChartCard
          title="逐题得分"
          hint="横轴=样本序号，纵轴=得分（看分歧）"
          className="lg:col-span-2"
        >
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={lineData} margin={{ top: 8, right: 8, bottom: 4, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f5f5f4" />
              <XAxis dataKey="idx" tick={{ fontSize: 9, fill: '#a8a29e' }} />
              <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: '#a8a29e' }} />
              <Tooltip
                labelFormatter={(idx: number) =>
                  `#${idx} ${lineData[idx - 1]?.q ?? ''}`
                }
                formatter={(v: number) => (v == null ? '—' : v.toFixed(2))}
              />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              {runs.map((run, i) => (
                <Line
                  key={String(run.id)}
                  name={shortRunName(run.name)}
                  type="monotone"
                  dataKey={run.name}
                  stroke={COLORS[i % COLORS.length]}
                  strokeWidth={1.6}
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* 逐样本胜负（相对基准） */}
      {winloss.length > 0 && (
        <div>
          <div className="mb-1.5 text-[11.5px] font-medium text-stone-600">
            逐样本胜负
            <span className="ml-1.5 text-[10.5px] font-normal text-stone-400">
              基准 {shortRunName(runs[0].name)} ｜ 均分{' '}
              {runs
                .map(r => {
                  const m = runMean(r);
                  return `${shortRunName(r.name)} ${m != null ? m.toFixed(2) : '—'}`;
                })
                .join(' · ')}
            </span>
          </div>
          <div className="space-y-1.5">
            {winloss.map(({ run, win, tie, loss }) => {
              const total = win + tie + loss || 1;
              return (
                <div
                  key={String(run.id)}
                  className="flex items-center gap-2.5 text-[11.5px]"
                >
                  <span
                    className="min-w-[150px] max-w-[200px] truncate text-stone-700"
                    title={run.name}
                  >
                    {shortRunName(run.name)}
                  </span>
                  <span className="tnum text-emerald-600">胜 {win}</span>
                  <span className="tnum text-stone-400">平 {tie}</span>
                  <span className="tnum text-rose-600">负 {loss}</span>
                  <div className="flex h-1.5 flex-1 overflow-hidden rounded-full bg-stone-100">
                    <div
                      className="bg-emerald-400"
                      style={{ width: `${(win / total) * 100}%` }}
                    />
                    <div
                      className="bg-stone-300"
                      style={{ width: `${(tie / total) * 100}%` }}
                    />
                    <div
                      className="bg-rose-400"
                      style={{ width: `${(loss / total) * 100}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

const ChartCard = ({
  title,
  hint,
  className,
  children,
}: {
  title: string;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) => (
  <div
    className={cn(
      'rounded-lg border border-stone-200 bg-white p-3',
      className,
    )}
  >
    <div className="mb-1 flex items-baseline gap-2">
      <span className="text-[11.5px] font-medium text-stone-700">{title}</span>
      {hint && <span className="text-[10px] text-stone-400">{hint}</span>}
    </div>
    {children}
  </div>
);
