/** 概览 tab —— 区间口径 KPI + 调用趋势 + 渠道/错误分布 + Top 应用/智能体（DataTable）。 */
import { useQuery } from '@tanstack/react-query';
import { Activity, Bot, Sparkles, Users } from 'lucide-react';

import { DataTable, type DataTableColumn } from '@/core/components/table';
import { Card, CardContent } from '@/core/components/ui/card';
import { StatTile, type StatTone } from '@/core/components/ui/stat-tile';
import { TimeSeriesChart } from '@/core/components/ui/time-series-chart';
import {
  formatDurationMs,
  formatNumber,
  formatPercent,
  formatTokens,
} from '@/core/lib/format';
import { DistributionCard } from '@/system/dashboard/components/distribution-card';
import { RankBadge } from '@/system/dashboard/components/rank-badge';
import {
  dashboardApi,
  type RangeParams,
} from '@/system/dashboard/services/dashboard';
import type { TopDimensionRow } from '@/system/dashboard/types/dashboard';

interface Props {
  params: RangeParams;
}

const makeTopCols = (max: number): DataTableColumn<TopDimensionRow>[] => [
  {
    key: 'label',
    header: '名称',
    render: (r, i) => (
      <div className="flex items-center gap-2">
        <RankBadge index={i} />
        <span className="truncate text-stone-700">
          {r.display_name ?? r.label}
        </span>
      </div>
    ),
  },
  {
    key: 'count',
    header: '调用',
    align: 'right',
    width: 160,
    render: r => (
      <div className="flex items-center justify-end gap-2">
        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-stone-100">
          <div
            className="from-primary-300 to-primary-500 h-full rounded-full bg-gradient-to-r"
            style={{ width: `${(r.count / max) * 100}%` }}
          />
        </div>
        <span className="tnum w-10 text-right text-stone-600">
          {formatNumber(r.count)}
        </span>
      </div>
    ),
  },
];

export const OverviewTab = ({ params }: Props) => {
  const overviewQ = useQuery({
    queryKey: ['dash', 'overview', params],
    queryFn: () => dashboardApi.overview(params),
  });
  const tsQ = useQuery({
    queryKey: ['dash', 'ts', params],
    queryFn: () => dashboardApi.timeseries({ ...params, granularity: 'auto' }),
  });
  const channelQ = useQuery({
    queryKey: ['dash', 'dist', 'channel', params],
    queryFn: () =>
      dashboardApi.distribution({ ...params, dimension: 'channel', limit: 6 }),
  });
  const errorQ = useQuery({
    queryKey: ['dash', 'dist', 'error_class', params],
    queryFn: () =>
      dashboardApi.distribution({
        ...params,
        dimension: 'error_class',
        limit: 6,
      }),
  });
  const appsQ = useQuery({
    queryKey: ['dash', 'top', 'app_id', params],
    queryFn: () =>
      dashboardApi.topDimension({ ...params, dimension: 'app_id', limit: 8 }),
  });
  const agentsQ = useQuery({
    queryKey: ['dash', 'top', 'agent_key', params],
    queryFn: () =>
      dashboardApi.topDimension({
        ...params,
        dimension: 'agent_key',
        limit: 8,
      }),
  });

  const o = overviewQ.data;
  const callsDelta = (() => {
    if (!o) return null;
    if (!o.prev_period_calls) return o.total_calls > 0 ? 1 : 0;
    return (o.total_calls - o.prev_period_calls) / o.prev_period_calls;
  })();
  const srDelta =
    o && o.prev_success_rate != null
      ? o.success_rate - o.prev_success_rate
      : null;
  const successTone: StatTone =
    (o?.success_rate ?? 1) > 0.95
      ? 'success'
      : (o?.success_rate ?? 1) > 0.8
        ? 'warning'
        : 'danger';
  const ttftText =
    o?.ttft_avg_ms != null ? formatDurationMs(o.ttft_avg_ms) : '—';
  const latencyText =
    o?.p95_duration_ms != null
      ? `P95 ${formatDurationMs(o.p95_duration_ms)}`
      : `平均 ${formatDurationMs(o?.avg_duration_ms)}`;

  const appMax = Math.max(...(appsQ.data ?? []).map(r => r.count), 1);
  const agentMax = Math.max(...(agentsQ.data ?? []).map(r => r.count), 1);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          label="调用量"
          value={formatNumber(o?.total_calls)}
          hint={`上一周期 ${formatNumber(o?.prev_period_calls)}`}
          delta={callsDelta}
          icon={Activity}
          tone="primary"
          loading={overviewQ.isLoading}
        />
        <StatTile
          label="成功率"
          value={formatPercent(o?.success_rate ?? 1)}
          hint={`${latencyText} · 首字 ${ttftText}`}
          delta={srDelta}
          icon={Sparkles}
          tone={successTone}
          loading={overviewQ.isLoading}
        />
        <StatTile
          label="Token 消耗"
          value={formatTokens(o?.total_tokens)}
          hint={`输入 ${formatTokens(o?.total_prompt_tokens)} · 输出 ${formatTokens(o?.total_completion_tokens)}`}
          icon={Bot}
          tone="primary"
          loading={overviewQ.isLoading}
        />
        <StatTile
          label="活跃终端用户"
          value={formatNumber(o?.active_end_users)}
          hint={`应用 ${formatNumber(o?.active_apps)} · 智能体 ${formatNumber(o?.active_agents)}`}
          icon={Users}
          tone="primary"
          loading={overviewQ.isLoading}
        />
      </div>

      <Card>
        <CardContent className="pt-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-medium text-stone-900">调用趋势</h3>
            <span className="text-[11px] text-stone-400">
              {tsQ.data
                ? `按${tsQ.data.granularity === 'day' ? '天' : '小时'}`
                : ''}
            </span>
          </div>
          <TimeSeriesChart
            data={tsQ.data?.points ?? []}
            xKey="ts"
            height={240}
            series={[
              {
                dataKey: 'total',
                name: '总调用',
                color: 'var(--color-primary-600)',
              },
              {
                dataKey: 'errors',
                name: '错误数',
                color: 'var(--color-red-500)',
              },
            ]}
            xTickFormatter={ts =>
              tsQ.data?.granularity === 'day'
                ? new Date(ts).toLocaleDateString('zh-CN', {
                    month: '2-digit',
                    day: '2-digit',
                  })
                : new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit' })
            }
            labelFormatter={ts => new Date(ts).toLocaleString('zh-CN')}
            empty="区间内暂无调用"
          />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DistributionCard
          title="渠道分布"
          rows={channelQ.data ?? []}
          loading={channelQ.isLoading}
        />
        <DistributionCard
          title="错误类型"
          rows={errorQ.data ?? []}
          loading={errorQ.isLoading}
          empty="区间内无错误"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardContent className="pt-5">
            <h3 className="mb-3 text-sm font-medium text-stone-900">Top 应用</h3>
            <DataTable
              columns={makeTopCols(appMax)}
              rows={appsQ.data ?? []}
              rowKey="label"
              loading={appsQ.isLoading}
              emptyText="暂无数据"
            />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5">
            <h3 className="mb-3 text-sm font-medium text-stone-900">
              Top 智能体
            </h3>
            <DataTable
              columns={makeTopCols(agentMax)}
              rows={agentsQ.data ?? []}
              rowKey="label"
              loading={agentsQ.isLoading}
              emptyText="暂无数据"
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
