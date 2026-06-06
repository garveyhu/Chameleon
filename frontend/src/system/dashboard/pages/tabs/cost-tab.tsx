/** 成本 tab —— 成本 KPI（含单位 token 成本）+ 成本趋势 + 维度下钻（DataTable，可排序）。 */
import { useState } from 'react';

import { useQuery } from '@tanstack/react-query';
import { Activity, Banknote, Coins, Gauge } from 'lucide-react';

import { DataTable, type DataTableColumn } from '@/core/components/table';
import { Card, CardContent } from '@/core/components/ui/card';
import { StatTile } from '@/core/components/ui/stat-tile';
import { TimeSeriesChart } from '@/core/components/ui/time-series-chart';
import { cn } from '@/core/lib/cn';
import {
  formatCost,
  formatNumber,
  formatPercent,
  formatTokens,
} from '@/core/lib/format';
import { RankBadge } from '@/system/dashboard/components/rank-badge';
import {
  dashboardApi,
  type RangeParams,
} from '@/system/dashboard/services/dashboard';
import type {
  CostDimensionRow,
  DimensionKey,
} from '@/system/dashboard/types/dashboard';

interface Props {
  params: RangeParams;
}

const DIMENSIONS: { key: DimensionKey; label: string }[] = [
  { key: 'app_id', label: '应用' },
  { key: 'agent_key', label: '智能体' },
  { key: 'model_code', label: '模型' },
  { key: 'channel', label: '渠道' },
  { key: 'end_user_id', label: '终端用户' },
  { key: 'session_id', label: '会话' },
];

const spanHours = (p: RangeParams): number => {
  if (!p.from_ts || !p.to_ts) return 24;
  return (new Date(p.to_ts).getTime() - new Date(p.from_ts).getTime()) / 3.6e6;
};

const sortVal = (r: CostDimensionRow, key: string): number => {
  switch (key) {
    case 'calls':
      return r.calls;
    case 'success_rate':
      return r.calls > 0 ? r.success_calls / r.calls : 0;
    case 'total_tokens':
      return r.total_tokens;
    case 'cost_usd':
    default:
      return r.cost_usd;
  }
};

const successBar = (r: CostDimensionRow): string => {
  const sr = r.calls > 0 ? r.success_calls / r.calls : 1;
  return sr > 0.95 ? 'bg-emerald-400' : sr > 0.8 ? 'bg-amber-400' : 'bg-red-400';
};

export const CostTab = ({ params }: Props) => {
  const [dimension, setDimension] = useState<DimensionKey>('app_id');
  const [sortKey, setSortKey] = useState('cost_usd');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  const totalsQ = useQuery({
    queryKey: ['cost', 'totals', params],
    queryFn: () => dashboardApi.costTotals(params),
  });
  const seriesQ = useQuery({
    queryKey: ['cost', 'series', params],
    queryFn: () =>
      dashboardApi.costTimeseries({
        ...params,
        bucket: spanHours(params) <= 48 ? 'hour' : 'day',
      }),
  });
  const dimQ = useQuery({
    queryKey: ['cost', 'dim', dimension, params],
    queryFn: () =>
      dashboardApi.costByDimension({ ...params, dimension, limit: 15 }),
  });

  const t = totalsQ.data;
  const avgCost = t && t.total_calls > 0 ? t.total_usd / t.total_calls : 0;
  const unitTokenCost =
    t && t.total_tokens > 0 ? (t.total_usd / t.total_tokens) * 1000 : 0;

  const rows = dimQ.data ?? [];
  const totalCost = totalsQ.data?.total_usd ?? 0;
  const sortedRows = [...rows].sort((a, b) => {
    const va = sortVal(a, sortKey);
    const vb = sortVal(b, sortKey);
    return sortOrder === 'asc' ? va - vb : vb - va;
  });

  const cols: DataTableColumn<CostDimensionRow>[] = [
    {
      key: 'name',
      header: '名称',
      render: (r, i) => (
        <div className="flex min-w-0 items-center gap-2">
          <RankBadge index={i} />
          <div className="min-w-0">
            <div className="truncate text-stone-700">
              {r.display_name ?? r.label}
            </div>
            {r.display_name && r.display_name !== r.label && (
              <div className="truncate font-mono text-[10px] text-stone-400">
                {r.label}
              </div>
            )}
          </div>
        </div>
      ),
    },
    {
      key: 'calls',
      header: '调用',
      align: 'right',
      sortable: true,
      width: 82,
      render: r => (
        <span className="tnum text-stone-600">{formatNumber(r.calls)}</span>
      ),
    },
    {
      key: 'success_rate',
      header: '成功率',
      align: 'right',
      sortable: true,
      width: 86,
      render: r => {
        const sr = r.calls > 0 ? r.success_calls / r.calls : 1;
        return (
          <span
            className={cn(
              'tnum',
              sr > 0.95
                ? 'text-emerald-600'
                : sr > 0.8
                  ? 'text-amber-600'
                  : 'text-red-600',
            )}
          >
            {formatPercent(sr)}
          </span>
        );
      },
    },
    {
      key: 'total_tokens',
      header: 'Token',
      align: 'right',
      sortable: true,
      width: 94,
      render: r => (
        <span className="tnum text-stone-500">
          {formatTokens(r.total_tokens)}
        </span>
      ),
    },
    {
      key: 'cost_usd',
      header: '成本',
      align: 'right',
      sortable: true,
      width: 106,
      render: r => (
        <span className="tnum font-semibold text-stone-800">
          {formatCost(r.cost_usd)}
        </span>
      ),
    },
    {
      key: 'share',
      header: '占比',
      width: 132,
      render: r => {
        const pct = totalCost > 0 ? (r.cost_usd / totalCost) * 100 : 0;
        return (
          <div className="flex items-center gap-2">
            <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-stone-100">
              <div
                className="from-primary-400 to-primary-600 h-full rounded-full bg-gradient-to-r"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="tnum w-8 text-right text-[10px] text-stone-400">
              {pct.toFixed(0)}%
            </span>
          </div>
        );
      },
    },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          label="区间总成本"
          value={formatCost(t?.total_usd)}
          delta={t?.delta_pct != null ? t.delta_pct / 100 : null}
          deltaInverse
          icon={Banknote}
          tone="success"
          loading={totalsQ.isLoading}
        />
        <StatTile
          label="调用次数"
          value={formatNumber(t?.total_calls)}
          icon={Activity}
          tone="neutral"
          loading={totalsQ.isLoading}
        />
        <StatTile
          label="平均单次成本"
          value={formatCost(avgCost)}
          icon={Gauge}
          tone="neutral"
          loading={totalsQ.isLoading}
        />
        <StatTile
          label="单位 Token 成本"
          value={`${formatCost(unitTokenCost)} / 1K`}
          hint={`共 ${formatTokens(t?.total_tokens)} token`}
          icon={Coins}
          tone="neutral"
          loading={totalsQ.isLoading}
        />
      </div>

      <Card>
        <CardContent className="pt-5">
          <h3 className="mb-3 text-sm font-medium text-stone-900">成本趋势</h3>
          <TimeSeriesChart
            data={seriesQ.data ?? []}
            xKey="ts"
            height={220}
            series={[
              {
                dataKey: 'cost_usd',
                name: '成本',
                color: 'var(--color-primary-600)',
              },
              {
                dataKey: 'total_tokens',
                name: 'Token',
                color: 'var(--color-amber-500)',
                axis: 'right',
              },
            ]}
            rightTickFormatter={v => formatTokens(v)}
            xTickFormatter={ts =>
              new Date(ts).toLocaleString('zh-CN', {
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
              })
            }
            labelFormatter={ts => new Date(ts).toLocaleString('zh-CN')}
            empty="区间内暂无成本数据"
          />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-5">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h3 className="text-sm font-medium text-stone-900">维度下钻</h3>
            <div className="inline-flex flex-wrap justify-end gap-0.5 rounded-md border border-stone-200 bg-white p-0.5">
              {DIMENSIONS.map(d => (
                <button
                  key={d.key}
                  type="button"
                  onClick={() => setDimension(d.key)}
                  className={cn(
                    'rounded px-2 py-0.5 text-[11.5px] transition',
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
          <DataTable
            columns={cols}
            rows={sortedRows}
            rowKey="label"
            leftBar={successBar}
            sortKey={sortKey}
            sortOrder={sortOrder}
            onSortChange={(k, o) => {
              setSortKey(k);
              setSortOrder(o);
            }}
            loading={dimQ.isLoading && !dimQ.data}
            refreshing={dimQ.isFetching}
            emptyText="区间内暂无成本数据"
            minWidth={680}
          />
        </CardContent>
      </Card>
    </div>
  );
};
