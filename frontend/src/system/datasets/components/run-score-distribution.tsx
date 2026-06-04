/** 分数分布桶（复用） —— 每 metric 一条直方图，点柱子回调上层做样本筛选。
 *  从原 run-detail-drawer 的 MetricHist 提出，供运行详情整页复用。 */

import { cn } from '@/core/lib/cn';
import type {
  MetricDistribution,
  ScoreBucket,
} from '@/system/datasets/types/dataset';

const bucketColor = (low: number): string =>
  low < 0.5 ? 'bg-red-300' : low < 0.8 ? 'bg-amber-300' : 'bg-emerald-300';

interface Props {
  metrics: MetricDistribution[];
  selected: ScoreBucket | null;
  onPick: (b: ScoreBucket) => void;
  loading?: boolean;
}

export const RunScoreDistribution = ({ metrics, selected, onPick, loading }: Props) => {
  if (metrics.length === 0) {
    return (
      <div className="py-4 text-center text-[11.5px] text-stone-400">
        {loading ? '加载中…' : '暂无评分数据'}
      </div>
    );
  }
  return (
    <>
      {metrics.map(m => (
        <MetricHist
          key={m.metric_name}
          metric={m}
          selected={selected}
          onPick={onPick}
        />
      ))}
    </>
  );
};

const MetricHist = ({
  metric,
  selected,
  onPick,
}: {
  metric: MetricDistribution;
  selected: ScoreBucket | null;
  onPick: (b: ScoreBucket) => void;
}) => {
  const max = Math.max(...metric.buckets.map(b => b.count), 1);
  return (
    <div className="mb-4">
      <div className="mb-1 flex items-center justify-between text-[11px]">
        <span className="text-stone-600">{metric.metric_name}</span>
        <span className="text-stone-400">
          均值 {metric.mean != null ? metric.mean.toFixed(2) : '—'}
        </span>
      </div>
      <div className="flex h-16 items-end gap-0.5">
        {metric.buckets.map((b, i) => {
          const active = !!selected && selected.low === b.low;
          const dimmed = !!selected && !active;
          return (
            <button
              key={i}
              type="button"
              onClick={() => onPick(b)}
              className="flex h-full flex-1 flex-col items-center justify-end"
              title={`[${b.low.toFixed(1)}, ${b.high.toFixed(1)}) · ${b.count} 条`}
            >
              <div
                className={cn(
                  'w-full rounded-t transition',
                  bucketColor(b.low),
                  active && 'ring-2 ring-stone-700 ring-offset-1',
                  dimmed && 'opacity-40',
                )}
                style={{ height: `${(b.count / max) * 100}%` }}
              />
            </button>
          );
        })}
      </div>
      <div className="flex justify-between text-[9px] text-stone-400">
        <span>0</span>
        <span>1</span>
      </div>
    </div>
  );
};
