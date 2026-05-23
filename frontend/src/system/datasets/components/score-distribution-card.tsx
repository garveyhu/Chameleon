/** 评分分布卡 —— P21.2 PR #64
 *
 * 接 /v1/admin/datasets/runs/:id/score-distribution：
 * - 每 metric 一个 SVG 直方图 + mean
 * - 低分（< threshold）item id 列表
 */

import { useQuery } from '@tanstack/react-query';
import { BarChart3, AlertTriangle } from 'lucide-react';

import { Skeleton } from '@/core/components/common/skeleton';
import { cn } from '@/core/lib/cn';
import type { EntityId } from '@/core/types/api';
import { evalTemplateApi } from '@/system/datasets/services/eval-template';
import type {
  MetricDistribution,
} from '@/system/datasets/types/eval-template';

interface Props {
  runId: EntityId;
  threshold?: number;
}

export const ScoreDistributionCard = ({ runId, threshold = 0.5 }: Props) => {
  const q = useQuery({
    queryKey: ['dataset-runs', runId, 'score-distribution', threshold],
    queryFn: () =>
      evalTemplateApi.scoreDistribution(runId, { threshold, buckets: 10 }),
    enabled: !!runId,
  });

  if (q.isLoading) return <Skeleton className="h-40 w-full" />;
  if (q.isError || !q.data) {
    return (
      <div className="rounded-md border border-stone-200 bg-stone-50 px-3 py-2 text-[11.5px] text-stone-500">
        加载分布失败或本 run 尚未跑评分模板
      </div>
    );
  }
  const data = q.data;
  if (data.metrics.length === 0) {
    return (
      <div className="rounded-md border border-stone-200 bg-stone-50 px-3 py-2 text-[11.5px] text-stone-500">
        本 run 没有 EvalTemplate 评分数据
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-[11.5px] text-stone-600">
        <BarChart3 className="h-3.5 w-3.5" />
        评分分布 · 共 {data.total_scored_items} items · threshold={threshold}
      </div>
      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        {data.metrics.map(m => (
          <MetricCard key={m.metric_name} metric={m} threshold={threshold} />
        ))}
      </div>
    </div>
  );
};

const MetricCard = ({
  metric,
  threshold,
}: {
  metric: MetricDistribution;
  threshold: number;
}) => {
  const maxCount = Math.max(...metric.buckets.map(b => b.count), 1);
  return (
    <div className="rounded-md border border-stone-200 bg-white px-3 py-2">
      <div className="flex items-baseline justify-between">
        <span className="font-mono text-[11.5px] font-medium text-stone-800">
          {metric.metric_name}
        </span>
        <span className="text-[11px] text-stone-500">
          mean ={' '}
          <span className="font-mono tnum text-stone-700">
            {metric.mean === null ? '—' : metric.mean.toFixed(3)}
          </span>
        </span>
      </div>
      <Histogram buckets={metric.buckets} maxCount={maxCount} threshold={threshold} />
      {metric.low_score_item_ids.length > 0 && (
        <div className="mt-1 flex items-start gap-1 text-[11px] text-rose-600">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
          <span>
            {metric.low_score_item_ids.length} item 低于 {threshold}：
            <span className="font-mono text-[10.5px] text-stone-500">
              {metric.low_score_item_ids
                .slice(0, 6)
                .map(String)
                .join(', ')}
              {metric.low_score_item_ids.length > 6 && '...'}
            </span>
          </span>
        </div>
      )}
    </div>
  );
};

const Histogram = ({
  buckets,
  maxCount,
  threshold,
}: {
  buckets: { low: number; high: number; count: number }[];
  maxCount: number;
  threshold: number;
}) => {
  const width = 220;
  const height = 60;
  const barW = width / buckets.length;
  return (
    <svg
      viewBox={`0 0 ${width} ${height + 12}`}
      className="mt-1 h-[72px] w-full"
    >
      {buckets.map((b, i) => {
        const h = (b.count / maxCount) * height;
        const isLow = b.high <= threshold;
        return (
          <g key={i}>
            <rect
              x={i * barW + 1}
              y={height - h}
              width={barW - 2}
              height={h}
              className={cn(
                isLow ? 'fill-rose-300' : 'fill-emerald-400',
              )}
            />
            <text
              x={i * barW + barW / 2}
              y={height + 9}
              textAnchor="middle"
              className="fill-stone-400 font-mono text-[8px]"
            >
              {b.low.toFixed(1)}
            </text>
          </g>
        );
      })}
    </svg>
  );
};
