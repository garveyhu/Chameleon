/** Dashboard 主页：DateRangePicker + 综合指标 + 时序图 + top agents/apps */

import { useQuery } from '@tanstack/react-query';
import { Activity, Bot, KeySquare, Sparkles } from 'lucide-react';
import { useMemo, useState } from 'react';

import { DateRangePicker, type DateRange } from '@/core/components/common/date-range-picker';
import { PageHeader } from '@/core/components/common/page-header';
import { Spinner } from '@/core/components/common/spinner';
import { Card, CardContent } from '@/core/components/ui/card';
import { StatTile } from '@/core/components/ui/stat-tile';
import { TimeSeriesChart } from '@/core/components/ui/time-series-chart';
import { formatNumber, formatPercent } from '@/core/lib/format';
import { dashboardApi } from '@/system/dashboard/services/dashboard';
import type { OverviewItem } from '@/system/dashboard/types/dashboard';

const defaultRange = (): DateRange => {
  const to = new Date();
  to.setHours(23, 59, 59, 999);
  const from = new Date();
  from.setDate(from.getDate() - 6);
  from.setHours(0, 0, 0, 0);
  return { from, to };
};

export const DashboardPage = () => {
  const [range, setRange] = useState<DateRange>(defaultRange);
  const params = useMemo(
    () => ({ from_ts: range.from.toISOString(), to_ts: range.to.toISOString() }),
    [range],
  );

  const overviewQ = useQuery({
    queryKey: ['dashboard', 'overview', params],
    queryFn: () => dashboardApi.overview(params),
  });
  const tsQ = useQuery({
    queryKey: ['dashboard', 'timeseries', params],
    queryFn: () => dashboardApi.timeseries({ ...params, granularity: 'auto' }),
  });
  const agentsQ = useQuery({
    queryKey: ['dashboard', 'top-agents', params],
    queryFn: () => dashboardApi.topAgents({ ...params, limit: 5 }),
  });
  const appsQ = useQuery({
    queryKey: ['dashboard', 'top-apps', params],
    queryFn: () => dashboardApi.topApps({ ...params, limit: 5 }),
  });

  const o: OverviewItem | undefined = overviewQ.data;
  const delta = (() => {
    if (!o || o.prev_period_calls === undefined || o.total_calls_in_range === undefined) return null;
    if (!o.prev_period_calls) return o.total_calls_in_range > 0 ? 1 : 0;
    return (o.total_calls_in_range - o.prev_period_calls) / o.prev_period_calls;
  })();

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <PageHeader title="Dashboard" description="按所选时间区间综合指标" />
        <DateRangePicker value={range} onChange={setRange} />
      </div>

      <div className="grid grid-cols-4 gap-4">
        <StatTile
          label="区间内调用"
          value={formatNumber(o?.total_calls_in_range ?? o?.total_calls_24h ?? 0)}
          hint={`上一周期 ${formatNumber(o?.prev_period_calls ?? 0)}`}
          delta={delta}
          icon={Activity}
          tone="primary"
        />
        <StatTile
          label="成功率 (24h)"
          value={formatPercent(o?.success_rate_24h ?? 1)}
          hint={`平均 ${(o?.avg_duration_ms_24h ?? 0).toFixed(0)} ms`}
          icon={Sparkles}
          tone={
            (o?.success_rate_24h ?? 1) > 0.95
              ? 'success'
              : (o?.success_rate_24h ?? 1) > 0.8
                ? 'warning'
                : 'danger'
          }
        />
        <StatTile
          label="Token 消耗 (24h)"
          value={formatNumber(
            (o?.total_prompt_tokens_24h ?? 0) + (o?.total_completion_tokens_24h ?? 0),
          )}
          hint={`提示 ${formatNumber(o?.total_prompt_tokens_24h ?? 0)} · 完成 ${formatNumber(o?.total_completion_tokens_24h ?? 0)}`}
          icon={Bot}
          tone="primary"
        />
        <StatTile
          label="活跃应用 (24h)"
          value={formatNumber(o?.active_apps_24h ?? 0)}
          hint={`活跃 agent ${o?.active_agents_24h ?? 0}`}
          icon={KeySquare}
          tone="primary"
        />
      </div>

      <div className="mt-6 grid grid-cols-3 gap-4">
        <Card className="col-span-2">
          <CardContent className="pt-5">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-medium text-stone-900">调用趋势</h3>
              <div className="flex items-center gap-2 text-[11px] text-stone-400">
                {tsQ.data?.granularity ? <span>按 {tsQ.data.granularity}</span> : null}
                {tsQ.isLoading && <Spinner size="sm" />}
              </div>
            </div>
            <TimeSeriesChart
              data={tsQ.data?.points ?? []}
              xKey="ts"
              height={256}
              series={[
                { dataKey: 'total', name: '总调用', color: 'var(--color-primary-600)' },
                { dataKey: 'errors', name: '错误数', color: '#ef4444' },
              ]}
              xTickFormatter={t =>
                tsQ.data?.granularity === 'day'
                  ? new Date(t).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
                  : new Date(t).toLocaleTimeString('zh-CN', { hour: '2-digit' })
              }
              labelFormatter={t => new Date(t).toLocaleString('zh-CN')}
            />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-5">
            <h3 className="mb-3 text-sm font-medium text-stone-900">Top Agents</h3>
            <ul className="space-y-2">
              {(agentsQ.data || []).map(a => (
                <li key={a.agent_key} className="flex items-center justify-between text-sm">
                  <span className="font-mono text-stone-700">{a.agent_key}</span>
                  <span className="text-stone-500">{formatNumber(a.count)}</span>
                </li>
              ))}
              {agentsQ.data?.length === 0 && (
                <li className="py-4 text-center text-xs text-stone-400">暂无数据</li>
              )}
            </ul>
          </CardContent>
        </Card>
      </div>

      <div className="mt-4">
        <Card>
          <CardContent className="pt-5">
            <h3 className="mb-3 text-sm font-medium text-stone-900">Top Apps</h3>
            <ul className="space-y-2">
              {(appsQ.data || []).map(a => (
                <li key={a.app_id} className="flex items-center justify-between text-sm">
                  <span className="font-mono text-stone-700">{a.app_id}</span>
                  <span className="text-stone-500">{formatNumber(a.count)}</span>
                </li>
              ))}
              {appsQ.data?.length === 0 && (
                <li className="py-4 text-center text-xs text-stone-400">暂无数据</li>
              )}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
