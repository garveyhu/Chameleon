/** Cost Dashboard 页 —— P22.1 PR #72
 *
 * 三个数据源：
 * - /cost/totals：卡片总额 + 上一周期 delta
 * - /cost/by-dimension：多维 top-N（agent_key / app_id / session_id）
 * - /cost/timeseries：时序折线（hour / day 分桶）
 */

import { useQuery } from '@tanstack/react-query';
import { ArrowDown, ArrowUp, DollarSign, TrendingUp } from 'lucide-react';
import { useMemo, useState } from 'react';

import { SectionCard } from '@/core/components/table';
import { cn } from '@/core/lib/cn';
import { dashboardApi } from '@/system/dashboard/services/dashboard';
import type {
  CostDimension,
  CostDimensionRow,
  CostTimeseriesPoint,
} from '@/system/dashboard/services/dashboard';

const PRESETS: { label: string; hours: number }[] = [
  { label: '24h', hours: 24 },
  { label: '7d', hours: 24 * 7 },
  { label: '30d', hours: 24 * 30 },
];

const DIMENSIONS: { key: CostDimension; label: string; c8?: boolean }[] = [
  { key: 'agent_key', label: 'Agent' },
  { key: 'app_id', label: 'App' },
  { key: 'session_id', label: 'Session' },
  { key: 'user_id', label: 'User', c8: true },
  { key: 'model_code', label: 'Model', c8: true },
  { key: 'channel_id', label: 'Channel', c8: true },
  { key: 'workspace_id', label: 'Workspace', c8: true },
];

export const CostDashboardPage = () => {
  const [hours, setHours] = useState(24);
  const [dimension, setDimension] = useState<CostDimension>('agent_key');

  const totalsQ = useQuery({
    queryKey: ['dashboard', 'cost', 'totals', hours],
    queryFn: () => dashboardApi.costTotals({ hours }),
  });
  const dimQ = useQuery({
    queryKey: ['dashboard', 'cost', 'by-dim', dimension, hours],
    queryFn: () =>
      dashboardApi.costByDimension({ dimension, hours, limit: 10 }),
    // user/model/channel/workspace 维度在 C8 接入前会失败，避免重试刷屏
    retry: false,
  });
  const seriesQ = useQuery({
    queryKey: ['dashboard', 'cost', 'series', hours],
    queryFn: () =>
      dashboardApi.costTimeseries({
        hours,
        bucket: hours <= 48 ? 'hour' : 'day',
      }),
  });

  return (
    <div className="space-y-3">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <DollarSign className="h-4 w-4 text-emerald-600" />
          <h1 className="text-[15px] font-medium text-stone-800">
            Cost Dashboard
          </h1>
        </div>
        <div className="inline-flex rounded-md border border-stone-200 bg-white p-0.5">
          {PRESETS.map(p => (
            <button
              key={p.hours}
              type="button"
              onClick={() => setHours(p.hours)}
              className={cn(
                'rounded px-2 py-0.5 text-[11.5px] transition',
                hours === p.hours
                  ? 'bg-stone-800 text-white'
                  : 'text-stone-600 hover:bg-stone-100',
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
      </header>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <TotalsCard
          title="区间总成本"
          value={totalsQ.data?.total_usd ?? 0}
          deltaPct={totalsQ.data?.delta_pct ?? null}
          loading={totalsQ.isLoading}
        />
        <TotalsCard
          title="调用次数"
          value={totalsQ.data?.total_calls ?? 0}
          isInt
          loading={totalsQ.isLoading}
        />
        <TotalsCard
          title="平均单次"
          value={
            totalsQ.data && totalsQ.data.total_calls > 0
              ? totalsQ.data.total_usd / totalsQ.data.total_calls
              : 0
          }
          loading={totalsQ.isLoading}
          precision={6}
        />
      </div>

      <SectionCard className="!p-3">
        <div className="mb-2 flex items-center gap-2">
          <TrendingUp className="h-3.5 w-3.5 text-stone-500" />
          <span className="text-[12.5px] font-medium text-stone-700">
            时间序列（{hours <= 48 ? '按小时' : '按天'}）
          </span>
        </div>
        <CostLineChart points={seriesQ.data ?? []} loading={seriesQ.isLoading} />
      </SectionCard>

      <SectionCard className="!p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="shrink-0 text-[12.5px] font-medium text-stone-700">
            Top by 维度
          </span>
          <div className="flex flex-wrap justify-end gap-0.5 rounded-md border border-stone-200 bg-white p-0.5">
            {DIMENSIONS.map(d => (
              <button
                key={d.key}
                type="button"
                onClick={() => setDimension(d.key)}
                className={cn(
                  'rounded px-2 py-0.5 text-[11px] transition',
                  dimension === d.key
                    ? 'bg-stone-800 text-white'
                    : 'text-stone-600 hover:bg-stone-100',
                )}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>
        <DimensionTable
          rows={dimQ.data ?? []}
          loading={dimQ.isLoading}
          error={dimQ.isError}
          dimension={dimension}
        />
      </SectionCard>
    </div>
  );
};

interface TotalsCardProps {
  title: string;
  value: number;
  deltaPct?: number | null;
  loading?: boolean;
  isInt?: boolean;
  precision?: number;
}

const TotalsCard = ({
  title,
  value,
  deltaPct,
  loading,
  isInt,
  precision = 4,
}: TotalsCardProps) => (
  <div className="rounded-md border border-stone-200/70 bg-white px-3 py-3">
    <div className="text-[11px] text-stone-500">{title}</div>
    <div className="mt-1 flex items-baseline gap-2">
      <span className="font-mono text-[20px] tnum text-stone-900">
        {loading
          ? '—'
          : isInt
            ? Math.round(value).toLocaleString()
            : `$${value.toFixed(precision)}`}
      </span>
      {deltaPct != null && (
        <span
          className={cn(
            'inline-flex items-center text-[10.5px] font-mono',
            deltaPct >= 0 ? 'text-rose-600' : 'text-emerald-600',
          )}
        >
          {deltaPct >= 0 ? (
            <ArrowUp className="h-3 w-3" />
          ) : (
            <ArrowDown className="h-3 w-3" />
          )}
          {Math.abs(deltaPct).toFixed(1)}%
        </span>
      )}
    </div>
  </div>
);

const CostLineChart = ({
  points,
  loading,
}: {
  points: CostTimeseriesPoint[];
  loading: boolean;
}) => {
  const max = useMemo(
    () => Math.max(...points.map(p => p.cost_usd), 0.001),
    [points],
  );
  if (loading) {
    return (
      <div className="py-8 text-center text-[11.5px] text-stone-400">
        加载中…
      </div>
    );
  }
  if (points.length === 0) {
    return (
      <div className="py-8 text-center text-[11.5px] text-stone-400">
        区间内暂无成本数据
      </div>
    );
  }

  const width = 800;
  const height = 120;
  const barW = width / Math.max(points.length, 1);
  return (
    <svg
      viewBox={`0 0 ${width} ${height + 20}`}
      className="h-32 w-full"
    >
      {points.map((p, i) => {
        const h = (p.cost_usd / max) * height;
        return (
          <rect
            key={i}
            x={i * barW + 1}
            y={height - h}
            width={barW - 2}
            height={h}
            className="fill-emerald-400"
          />
        );
      })}
      <text
        x={2}
        y={height + 14}
        className="fill-stone-400 font-mono text-[8px]"
      >
        {new Date(points[0].ts).toLocaleString()}
      </text>
      <text
        x={width - 2}
        y={height + 14}
        textAnchor="end"
        className="fill-stone-400 font-mono text-[8px]"
      >
        {new Date(points[points.length - 1].ts).toLocaleString()}
      </text>
    </svg>
  );
};

const DimensionTable = ({
  rows,
  loading,
  error,
  dimension,
}: {
  rows: CostDimensionRow[];
  loading: boolean;
  error?: boolean;
  dimension: CostDimension;
}) => {
  const max = Math.max(...rows.map(r => r.cost_usd), 0.001);
  const needsC8 = DIMENSIONS.find(d => d.key === dimension)?.c8;
  if (loading) {
    return (
      <div className="py-6 text-center text-[11.5px] text-stone-400">
        加载中…
      </div>
    );
  }
  if ((error || rows.length === 0) && needsC8) {
    return (
      <div className="py-6 text-center text-[11.5px] text-stone-400">
        该维度依赖后端 cost_by_dimension 多维聚合（Agent C C8）；接入后自动展示
      </div>
    );
  }
  if (rows.length === 0) {
    return (
      <div className="py-6 text-center text-[11.5px] text-stone-400">
        无数据
      </div>
    );
  }
  return (
    <table className="w-full text-[12px]">
      <thead className="text-[10.5px] text-stone-500">
        <tr>
          <th className="px-2 py-1 text-left">label</th>
          <th className="px-2 py-1 text-right">cost (USD)</th>
          <th className="px-2 py-1 text-right">calls</th>
          <th className="w-1/3 px-2 py-1" />
        </tr>
      </thead>
      <tbody className="divide-y divide-stone-100">
        {rows.map(r => (
          <tr key={r.label} className="hover:bg-warm-2/20">
            <td className="px-2 py-1 font-mono text-stone-700">{r.label}</td>
            <td className="px-2 py-1 text-right font-mono tnum text-stone-800">
              {r.cost_usd.toFixed(4)}
            </td>
            <td className="px-2 py-1 text-right font-mono tnum text-stone-500">
              {r.calls}
            </td>
            <td className="px-2 py-1">
              <div className="relative h-2 w-full overflow-hidden rounded bg-stone-100">
                <div
                  className="absolute inset-y-0 left-0 bg-emerald-300"
                  style={{ width: `${(r.cost_usd / max) * 100}%` }}
                />
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};
