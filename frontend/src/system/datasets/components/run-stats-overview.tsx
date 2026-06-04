/** 运行统计概览 —— 概览卡（总样本 / 总运行 / 最佳 / 最近）+ 平均分趋势折线。模块 F。 */

import { TimeSeriesChart } from '@/core/components/ui/time-series-chart';
import { cn } from '@/core/lib/cn';
import { formatScore } from '@/core/lib/score';
import type { DatasetRunRow } from '@/system/datasets/types/dataset';

const meanOf = (r: DatasetRunRow): number | null => {
  const s = r.summary as Record<string, unknown> | null;
  const v = s?.mean_score ?? s?.mean ?? s?.avg_score;
  return typeof v === 'number' ? v : null;
};

interface Props {
  runs: DatasetRunRow[];
  itemCount: number;
}

export const RunStatsOverview = ({ runs, itemCount }: Props) => {
  // 时间升序（老→新），仅取有均分的运行画趋势
  const ordered = [...runs].sort((a, b) =>
    a.created_at.localeCompare(b.created_at),
  );
  const scored = ordered.filter(r => meanOf(r) != null);
  const means = scored.map(r => meanOf(r) as number);
  const best = means.length ? Math.max(...means) : null;
  const bestRun = best != null ? scored.find(r => meanOf(r) === best) : null;
  const last = means.length ? means[means.length - 1] : null;
  const prev = means.length > 1 ? means[means.length - 2] : null;
  const delta = last != null && prev != null ? last - prev : null;

  const trend = scored.map((r, i) => ({
    idx: `#${i + 1}`,
    mean: meanOf(r) as number,
  }));

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-4 gap-3">
        <StatCard label="总样本" value={String(itemCount)} />
        <StatCard label="总运行" value={String(runs.length)} />
        <StatCard
          label="最佳平均分"
          value={best != null ? formatScore(best) : '—'}
          sub={bestRun?.name}
        />
        <StatCard
          label="最近平均分"
          value={last != null ? formatScore(last) : '—'}
          sub={
            delta != null
              ? `${delta >= 0 ? '↑' : '↓'} ${Math.abs(delta).toFixed(2)}`
              : undefined
          }
          subClass={
            delta != null
              ? delta >= 0
                ? 'text-emerald-600'
                : 'text-rose-600'
              : undefined
          }
        />
      </div>
      <div className="rounded-lg border border-stone-200 p-3">
        <div className="mb-1 text-[12px] font-medium text-stone-700">
          运行趋势（平均分）
        </div>
        <TimeSeriesChart
          data={trend}
          xKey="idx"
          series={[
            {
              dataKey: 'mean',
              name: '平均分',
              color: 'var(--color-primary-600)',
            },
          ]}
          height={170}
          empty="还没有评分运行，跑一次后出现趋势"
        />
      </div>
    </div>
  );
};

interface StatCardProps {
  label: string;
  value: string;
  sub?: string;
  subClass?: string;
}

const StatCard = ({ label, value, sub, subClass }: StatCardProps) => (
  <div className="rounded-lg border border-stone-200 bg-white px-3 py-2.5">
    <div className="text-[11px] text-stone-500">{label}</div>
    <div className="mt-0.5 text-[19px] font-semibold tabular-nums text-stone-900">
      {value}
    </div>
    {sub && (
      <div
        className={cn('mt-0.5 truncate text-[10.5px] text-stone-400', subClass)}
        title={sub}
      >
        {sub}
      </div>
    )}
  </div>
);
